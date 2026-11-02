import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from string import Template
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ..domain.errors import LlmUnavailableError
from ..domain.llm import (
    Extraction,
    ExtractionRequest,
    Reply,
    ReplyIntent,
    ReplyRequest,
    TokenUsage,
)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class PromptFile:
    """A prompt template ($placeholders) and the version it is logged under."""

    version: str
    template: str


def _usage(message: AIMessage) -> TokenUsage:
    usage = message.usage_metadata or {}
    return TokenUsage(usage.get("input_tokens", 0), usage.get("output_tokens", 0))


def _content(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(
        part.get("text", "") if isinstance(part, dict) else str(part) for part in message.content
    )


def _parse_json(text: str) -> dict[str, Any]:
    match = _JSON_OBJECT.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def strip_introduction(text: str, agent_name: str) -> str:
    """Drops an opening self-introduction ("¡Hola! Soy Sofía, de Inmobiliaria Sur.") and keeps
    the rest. A plain greeting without the agent's name is left alone, so nothing else is
    lost; text that is only the introduction is returned unchanged."""
    if not agent_name.strip():
        return text
    pattern = re.compile(
        r"^\s*(?:¡?\s*hola\s*!?[,.]?\s*)?"
        rf"(?:soy|te habla|mi nombre es)\s+{re.escape(agent_name.strip())}\b[^.!?¿]*[.!]\s*",
        re.IGNORECASE,
    )
    rest = pattern.sub("", text, count=1)
    if not rest or rest == text:
        return text
    return rest[0].upper() + rest[1:]


class LangChainLanguageModel:
    """LanguageModel on any LangChain chat model.

    Extraction asks for a JSON object in plain text instead of provider-specific structured
    output, so every provider behaves the same; values are validated by the caller.
    """

    def __init__(
        self, chat_model: BaseChatModel, model_name: str, extract: PromptFile, reply: PromptFile
    ) -> None:
        self._chat_model = chat_model
        self._model_name = model_name
        self._extract = extract
        self._reply = reply

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def prompt_versions(self) -> Mapping[str, str]:
        return {"extract": self._extract.version, "reply": self._reply.version}

    def _invoke(self, messages: list[BaseMessage]) -> AIMessage:
        try:
            result = self._chat_model.invoke(messages)
        except Exception as error:  # timeouts, rate limits, provider outages
            raise LlmUnavailableError(f"{type(error).__name__} from the model provider.") from error
        if not isinstance(result, AIMessage):
            raise LlmUnavailableError("The model returned an unexpected message type.")
        return result

    def extract(self, request: ExtractionRequest) -> Extraction:
        questions = [
            {
                "key": question.key,
                "label": question.label,
                "kind": question.kind.value,
                "options": list(question.options),
            }
            for question in request.questions
        ]
        transcript = "\n".join(f"{line.author.value}: {line.text}" for line in request.transcript)
        system = Template(self._extract.template).safe_substitute(
            questions=json.dumps(questions, ensure_ascii=False),
            transcript=transcript or "(sin mensajes previos)",
            asked_key=request.asked_key or "",
            wants_name="sí" if request.wants_name else "no",
            wants_contact="sí" if request.wants_contact else "no",
            choices=json.dumps(
                [{"id": choice.id, "label": choice.label} for choice in request.choices],
                ensure_ascii=False,
            ),
        )
        result = self._invoke([SystemMessage(system), HumanMessage(request.latest)])
        parsed = _parse_json(_content(result))
        values = parsed.get("answers")
        name = parsed.get("visitor_name")
        contact = parsed.get("contact")
        choice_id = parsed.get("choice_id")
        offered = {choice.id for choice in request.choices}
        return Extraction(
            values=values if isinstance(values, dict) else {},
            visitor_name=name if isinstance(name, str) and name.strip() else None,
            contact=contact if isinstance(contact, str) and contact.strip() else None,
            # Only an id the agent actually offered; anything else is ignored.
            choice_id=choice_id if isinstance(choice_id, str) and choice_id in offered else None,
            wants_human=parsed.get("wants_human") is True,
            usage=_usage(result),
        )

    def compose_reply(self, request: ReplyRequest) -> Reply:
        """Words the reply. Only GREET may introduce the agent: if the model opens any other
        message with "(¡Hola!) Soy <agent>…", that sentence is dropped."""
        question = request.question
        system = Template(self._reply.template).safe_substitute(
            intent=request.intent.value,
            tone=request.tone.value,
            agent_name=request.agent_name,
            business_name=request.business_name,
            question=question.label if question else "",
            options=", ".join(question.options) if question else "",
            facts=json.dumps(dict(request.facts), ensure_ascii=False),
        )
        result = self._invoke([SystemMessage(system), HumanMessage("Escribí el mensaje.")])
        text = _content(result).strip()
        if request.intent is not ReplyIntent.GREET:
            text = strip_introduction(text, request.agent_name)
        if not text:
            raise LlmUnavailableError("The model returned an empty reply.")
        return Reply(text=text, usage=_usage(result))
