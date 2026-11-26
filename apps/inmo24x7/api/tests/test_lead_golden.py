"""Golden conversations: whole chats through the real lead graph and LangGraph runtime, the
fake model and a pinned clock. Each one pins every outbound message (author, text and
payload) and the final graph state, so a change in the flow shows up as a diff.

The fixtures live in tests/golden/<name>.json. To rewrite them on purpose:

    uv run --all-packages pytest apps/inmo24x7/api/tests/test_lead_golden.py --update-golden

then review the JSON diff like any other change.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from followup_core.conversation.application.threads import HandledTurn, HandleIncomingMessage
from followup_core.conversation.domain.runtime import BusinessContext
from followup_core.conversation.domain.thread import (
    Author,
    Channel,
    Direction,
    InboundPart,
    Message,
    Thread,
    ThreadKey,
    release,
    take_over,
)
from followup_core.tenancy.domain.agent_config import AgentConfig
from inmo24x7_api.properties.domain.conditions import (
    ConditionSettings,
    Guarantee,
    PropertyConditions,
)
from inmo24x7_api.properties.domain.property import Currency, Operation
from inmo24x7_api.properties.domain.reference import web_property_text
from inmo24x7_api.properties.domain.search import Listing
from lead_fakes import DEFAULTS, TIMEZONE, TUESDAY_11, WEEKDAYS_9_18, Chat, ListingSearch

GOLDEN_DIR = Path(__file__).parent / "golden"
TENANT = UUID("00000000-0000-0000-0000-00000000a001")
VISITOR = "visitor.golden"
TEAM_PROFILE = UUID("00000000-0000-0000-0000-00000000b001")


# --- In-memory conversation storage (the same use case the API runs) -------------------


class Threads:
    def __init__(self) -> None:
        self.by_key: dict[str, Thread] = {}

    def get_by_key(self, key: ThreadKey) -> Thread | None:
        return self.by_key.get(str(key))

    def get_by_id(self, thread_id: UUID) -> Thread | None:
        return next((t for t in self.by_key.values() if t.id == thread_id), None)

    def count_started_by(self, tenant_id: UUID, channel: Channel, profile_id: UUID) -> int:
        return 0

    def add(self, thread: Thread) -> None:
        self.by_key[str(thread.key)] = thread

    def touch(self, thread_id: UUID, last_message_at: datetime) -> None:
        for key, thread in self.by_key.items():
            if thread.id == thread_id:
                self.by_key[key] = replace(thread, last_message_at=last_message_at)

    def set_control(self, thread: Thread) -> None:
        self.by_key[str(thread.key)] = thread


class Messages:
    def __init__(self) -> None:
        self.items: list[Message] = []

    def append(self, message: Message) -> None:
        self.items.append(message)

    def list_for_thread(self, thread_id: UUID) -> Sequence[Message]:
        return [m for m in self.items if m.thread_id == thread_id]

    def count_inbound_since(self, tenant_id: UUID, channel: Channel, since: datetime) -> int:
        return 0


class NoLock:
    def acquire(self, key: ThreadKey) -> None:
        return None


class Configs:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def current(self, tenant_id: UUID) -> tuple[int, AgentConfig]:
        return 1, self.config

    def at_version(self, tenant_id: UUID, version: int) -> AgentConfig:
        return self.config


class Clock:
    """Pinned; every message moves it one minute, so the transcript stays in order."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def tick(self) -> None:
        self.now = self.now + timedelta(minutes=1)


# --- Steps of a scripted conversation ---------------------------------------------------


@dataclass(frozen=True)
class Say:
    text: str
    # "slot:<n>" / "card:<n>": tap the n-th slot or card the agent offered last.
    tap: str | None = None


@dataclass(frozen=True)
class Burst:
    """Several messages before the agent answers; ("audio", text) is a transcribed voice
    note."""

    parts: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TakeOver:
    pass


@dataclass(frozen=True)
class TeamWrites:
    text: str


@dataclass(frozen=True)
class Release:
    pass


Step = Say | Burst | TakeOver | TeamWrites | Release


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    steps: tuple[Step, ...]
    config: AgentConfig = DEFAULTS
    listings: Sequence[Listing] | None = None
    policy: ConditionSettings | None = None
    visitor_contact: str | None = None
    channel: Channel = Channel.SIMULATOR
    llm: Callable[[], Any] | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


class PolicySearch(ListingSearch):
    def __init__(self, listings: Sequence[Listing], settings: ConditionSettings | None) -> None:
        super().__init__(listings)
        self.settings = settings or ConditionSettings()

    def policy(self, tenant_id: UUID) -> ConditionSettings:
        return self.settings


class Conversation:
    """Drives HandleIncomingMessage over the real runtime of lead_fakes.Chat."""

    def __init__(self, scenario: Scenario) -> None:
        listings = scenario.listings
        search = (
            PolicySearch(listings, scenario.policy) if listings is not None else ListingSearch()
        )
        llm = scenario.llm() if scenario.llm else None
        self.chat = Chat(scenario.config, search=search, llm=llm)
        self.clock = Clock(TUESDAY_11)
        self.threads = Threads()
        self.messages = Messages()
        self.key = ThreadKey(TENANT, scenario.channel, VISITOR)
        self.scenario = scenario
        business = BusinessContext(TENANT, "Inmobiliaria Sur", TIMEZONE, WEEKDAYS_9_18)
        self.use_case = HandleIncomingMessage(
            self.threads,
            self.messages,
            NoLock(),
            self.chat.runtime,
            Configs(scenario.config),
            lambda _tenant: business,
            clock=self.clock,
        )
        self.last_payloads: dict[str, list[dict[str, Any]]] = {"slots": [], "cards": []}

    def _tap(self, tap: str | None) -> str | None:
        if tap is None:
            return None
        kind, _, index = tap.partition(":")
        return self.last_payloads[kind + "s"][int(index)]["id"]

    def run(self) -> dict[str, Any]:
        turns: list[dict[str, Any]] = []
        for step in self.scenario.steps:
            self.clock.tick()
            if isinstance(step, Say):
                handled = self.use_case.execute(
                    self.key,
                    step.text,
                    choice_id=self._tap(step.tap),
                    visitor_contact=self.scenario.visitor_contact,
                )
                turns.append(self._turn({"say": step.text, "tap": step.tap}, handled))
            elif isinstance(step, Burst):
                parts = [InboundPart(text, content_type=kind) for kind, text in step.parts]
                handled = self.use_case.execute(
                    self.key, parts, visitor_contact=self.scenario.visitor_contact
                )
                turns.append(self._turn({"burst": [list(p) for p in step.parts]}, handled))
            elif isinstance(step, TakeOver):
                thread = self._thread()
                taken, event = take_over(thread, TEAM_PROFILE, "Ana", self.clock())
                self.threads.set_control(taken)
                self.messages.append(event)
                turns.append({"in": {"take_over": True}, "out": []})
            elif isinstance(step, TeamWrites):
                thread = self._thread()
                self.messages.append(
                    Message(
                        uuid4(),
                        thread.id,
                        Direction.OUTBOUND,
                        Author.HUMAN,
                        step.text,
                        self.clock(),
                        author_profile_id=TEAM_PROFILE,
                    )
                )
                turns.append({"in": {"team": step.text}, "out": []})
            elif isinstance(step, Release):
                released, event = release(self._thread(), "Ana", self.clock())
                self.threads.set_control(released)
                if event is not None:
                    self.messages.append(event)
                turns.append({"in": {"release": True}, "out": []})
        state = dict(self.chat.runtime.state(self.key))
        return _plain(
            {
                "description": self.scenario.description,
                "turns": turns,
                "intents": [r.intent.value for r in self.chat.llm.replies],
                "model_calls": self.chat.llm.calls,
                "state": state,
            }
        )

    def _thread(self) -> Thread:
        thread = self.threads.get_by_key(self.key)
        assert thread is not None, "the conversation has not started"
        return thread

    def _turn(self, said: dict[str, Any], handled: HandledTurn) -> dict[str, Any]:
        out = []
        for message in handled.outbound:
            payload = message.payload or None
            if payload:
                for kind in ("slots", "cards"):
                    if payload.get(kind):
                        self.last_payloads[kind] = list(payload[kind])
            out.append({"author": message.author.value, "text": message.text, "payload": payload})
        return {
            "in": {key: value for key, value in said.items() if value is not None},
            "agent_paused": handled.agent_paused,
            "opt_out": handled.opt_out,
            "out": out,
        }


def _plain(value: Any) -> Any:
    """JSON-only values, keys sorted: what the fixture stores."""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


# --- The listings of the condition scenarios --------------------------------------------


def _listing(slug: str, street: str, price: int, **conditions: Any) -> Listing:
    return Listing(
        id=f"00000000-0000-0000-0000-{slug:0>12}",
        title="2 ambientes",
        address=f"{street} 4800",
        operation=Operation.RENT,
        zone="Palermo",
        price=price,
        currency=Currency.ARS,
        rooms=2,
        link=f"https://x.test/{street.lower()}",
        is_sample=False,
        conditions=PropertyConditions(**conditions),
    )


CAUCION = frozenset({Guarantee.CAUCION})
GORRITI = _listing("1", "Gorriti", 800_000, garantias=CAUCION, contrato_minimo_meses=24)
HONDURAS = _listing("2", "Honduras", 900_000)
THAMES = _listing("3", "Thames", 700_000, contrato_minimo_meses=24)
MALABIA = _listing("4", "Malabia", 750_000, contrato_minimo_meses=24)
WEB_GORRITI = Listing(
    id="00000000-0000-0000-0000-000000000005",
    title="2 ambientes luminoso",
    address="Gorriti 4800",
    operation=Operation.RENT,
    zone="Palermo",
    price=850_000,
    currency=Currency.ARS,
    rooms=2,
    link="https://www.inmosur.com.ar/propiedades/gorriti-4800",
    is_sample=False,
)


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "rent_visit_by_text",
        "Rent in Palermo, a property picked by text, a slot tapped, name and email: a visit "
        "hand-off; then a message after the hand-off.",
        (
            Say("Hola"),
            Say("Quiero alquilar"),
            Say("Palermo"),
            Say("Me interesa la primera"),
            Say("el primero", tap="slot:0"),
            Say("Me llamo Ana Pérez"),
            Say("ana@example.com"),
            Say("¿y cuándo me llaman?"),
        ),
    ),
    Scenario(
        "sale_qualified",
        "Buying: every question answered, the visit declined: a qualified hand-off, then two "
        "messages after it.",
        (
            Say("Hola"),
            Say("Quiero comprar"),
            Say("Belgrano"),
            Say("hasta 200 mil dólares"),
            Say("3"),
            Say("me llamo Juan Gómez"),
            Say("juan@example.com"),
            Say("no, gracias"),
            Say("gracias!"),
            Say("¿me escriben hoy?"),
        ),
    ),
    Scenario(
        "human_request",
        "The lead asks for a person mid-flow: a human hand-off; later messages after it.",
        (
            Say("Hola, quiero alquilar en Palermo"),
            Say("Prefiero hablar con una persona"),
            Say("¿hola?"),
        ),
    ),
    Scenario(
        "web_button_whatsapp",
        "The website button names a property on WhatsApp (the contact comes from the "
        "channel): greeted, its slots right away, a slot tapped, the name, a visit hand-off.",
        (
            Say(web_property_text(WEB_GORRITI.title, WEB_GORRITI.link)),
            Say("el segundo", tap="slot:1"),
            Say("Me llamo Laura Díaz"),
        ),
        listings=(WEB_GORRITI,),
        visitor_contact="+54 9 11 5555-0188",
        channel=Channel.WHATSAPP,
    ),
    Scenario(
        "property_tap_then_other_property",
        "A card tapped, a slot tapped, then another card tapped: its own slots replace the visit.",
        (
            Say("Hola"),
            Say("Quiero alquilar"),
            Say("Palermo"),
            Say("esta", tap="card:0"),
            Say("ese", tap="slot:0"),
            Say("mejor la otra", tap="card:1"),
            Say("ese", tap="slot:1"),
        ),
    ),
    Scenario(
        "requirement_yes",
        "A chosen property asks for caución; the lead says they can get it: slots, a pick.",
        (
            Say("Hola"),
            Say("Quiero alquilar por 2 años con garantía propietaria"),
            Say("Palermo"),
            Say("Me interesa la de Gorriti"),
            Say("sí, consigo el seguro"),
            Say("ese", tap="slot:0"),
        ),
        listings=(GORRITI, HONDURAS),
    ),
    Scenario(
        "requirement_no",
        "The decisive question (garantía), then the requirement said plainly; the lead "
        "cannot meet it: the fitting option is suggested.",
        (
            Say("Hola"),
            Say("Quiero alquilar por 1 mes"),
            Say("Palermo"),
            Say("Me interesa la de Gorriti"),
            Say("No tengo garantía"),
            Say("no puedo"),
        ),
        listings=(GORRITI, HONDURAS),
    ),
    Scenario(
        "requirement_unclear_twice",
        "An unclear answer to the requirement is asked once more in other words; a second "
        "unclear answer goes on with the conversation.",
        (
            Say("Hola"),
            Say("Quiero alquilar por 2 años con garantía propietaria"),
            Say("Palermo"),
            Say("Me interesa la de Gorriti"),
            Say("mmm no sé"),
            Say("capaz más adelante"),
        ),
        listings=(GORRITI, HONDURAS),
    ),
    Scenario(
        "nothing_fits_relax_yes",
        "Every option asks for a 2-year contract and the lead wants 1 month: asked once if "
        "they would consider it; yes shows the options again.",
        (
            Say("Hola"),
            Say("Quiero alquilar por 1 mes"),
            Say("Palermo"),
            Say("sí, me interesa verlas"),
        ),
        listings=(THAMES, MALABIA),
    ),
    Scenario(
        "nothing_fits_relax_no",
        "The same, and the lead says no: nothing fits, the team will let them know.",
        (
            Say("Hola"),
            Say("Quiero alquilar por 1 mes"),
            Say("Palermo"),
            Say("no"),
            Say("ok gracias"),
        ),
        listings=(THAMES, MALABIA),
    ),
    Scenario(
        "no_options_then_more_messages",
        "No listing in the zone: no options, then the flow keeps asking; several turns that "
        "make no commercial progress.",
        (
            Say("Hola, quiero alquilar en Mataderos"),
            Say("¿no tienen nada?"),
            Say("bueno"),
            Say("¿y ahora?"),
            Say("dale"),
            Say("¿hay algo?"),
        ),
    ),
    Scenario(
        "opt_out_baja",
        "A plain BAJA: the fixed confirmation and nothing else, without a model call.",
        (Say("Hola"), Say("Quiero alquilar"), Say("BAJA")),
    ),
    Scenario(
        "opt_out_by_the_model",
        "An opt-out in other words, read by the model.",
        (Say("Hola"), Say("no me molesten más")),
    ),
    Scenario(
        "voice_note_burst",
        "A burst on WhatsApp: a text and a transcribed voice note, read together in one turn.",
        (
            Burst((("text", "hola"), ("audio", "busco un dos ambientes para alquilar en Palermo"))),
            Burst((("audio", "me interesa la primera"),)),
        ),
        visitor_contact="+54 9 11 5555-0188",
        channel=Channel.WHATSAPP,
    ),
    Scenario(
        "taken_over_and_released",
        "The team takes the conversation: messages are stored, not answered; after the "
        "release the agent reads what it missed with the new message.",
        (
            Say("Hola"),
            Say("Quiero alquilar"),
            TakeOver(),
            Say("en Palermo"),
            TeamWrites("¿Qué presupuesto tenés?"),
            Say("hasta 800 mil pesos"),
            Release(),
            Say("2 ambientes"),
        ),
    ),
    Scenario(
        "slot_changed_after_hand_off",
        "After a visit hand-off the reply buttons still change the time; the same slot "
        "again changes nothing.",
        (
            Say("Hola"),
            Say("Quiero alquilar"),
            Say("Palermo"),
            Say("Me interesa la primera"),
            Say("ese", tap="slot:0"),
            Say("Me llamo Ana Pérez"),
            Say("ana@example.com"),
            Say("mejor el otro", tap="slot:1"),
            Say("el otro", tap="slot:1"),
        ),
    ),
)


def _fixture(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.json"


def test_the_set_covers_at_least_fifteen_conversations() -> None:
    assert len(SCENARIOS) >= 15
    assert len({scenario.name for scenario in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_golden_conversation(scenario: Scenario, request: pytest.FixtureRequest) -> None:
    got = Conversation(scenario).run()
    path = _fixture(scenario.name)
    if request.config.getoption("--update-golden"):
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps(got, ensure_ascii=False, indent=2) + "\n", "utf-8")
        return
    assert path.exists(), f"No golden for {scenario.name}: run with --update-golden."
    expected = json.loads(path.read_text("utf-8"))
    assert got == expected


@pytest.mark.parametrize("scenario", SCENARIOS[:3], ids=lambda scenario: scenario.name)
def test_a_conversation_is_the_same_every_time(scenario: Scenario) -> None:
    assert Conversation(scenario).run() == Conversation(scenario).run()
