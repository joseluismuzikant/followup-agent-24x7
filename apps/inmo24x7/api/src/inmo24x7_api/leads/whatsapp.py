"""How the lead agent's messages look on WhatsApp (the product's `MessageRenderer`)."""

from typing import Any
from urllib.parse import urljoin

from followup_core.conversation.domain.thread import Author, Message
from followup_core.messaging.domain.outbound import (
    MAX_BUTTON_TITLE,
    MAX_BUTTONS,
    buttons_body,
    list_body,
    text_bodies,
)

OVER_BUDGET_NOTE = "Un poco más de tu presupuesto"
PICK_PROMPT = "¿Cuál te interesa?"
PICK_LIST_BUTTON = "Ver opciones"


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def pick_body(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """One message to pick a card, like the visit slots: reply buttons titled with the
    address (titles like "2 ambientes" repeat) for up to 3 cards, a list otherwise."""
    if len(cards) <= MAX_BUTTONS:
        return buttons_body(
            PICK_PROMPT,
            [(card["id"], _short(str(card["address"]), MAX_BUTTON_TITLE)) for card in cards],
        )
    return list_body(
        PICK_PROMPT,
        PICK_LIST_BUTTON,
        [
            (
                card["id"],
                _short(str(card["title"]), 24),
                _short(f"{card['address']} · {card['price_label']}", 72),
            )
            for card in cards
        ],
    )


def card_text(card: dict[str, Any], link: str) -> str:
    lines = [f"*{card['title']}*", str(card["address"]), str(card["price_label"])]
    if card.get("over_budget"):
        lines.append(OVER_BUDGET_NOTE)
    lines.append(link)
    return "\n".join(lines)


class LeadMessageRenderer:
    """- text → text messages (split above 4,096 characters);
    - property cards → the intro text, then one message per card with the title in bold,
      address, price, the over-budget note and the listing link (with its preview), then
      one message to pick one (`pick_body`: reply buttons, or a list above 3 cards);
    - visit slots → reply buttons (ids are the slot ids, titles "jue 6/11 10:30");
    - a template the team sends outside the 24-hour window (the visit confirmation) → that
      template, as stored in the payload;
    - system messages (the hand-off event) → nothing: they are never sent to the lead.
    """

    def __init__(self, panel_url: str) -> None:
        # Sample listings link to the panel's /ejemplo pages, which need an absolute URL.
        self._panel_url = panel_url.rstrip("/") + "/"

    def __call__(self, message: Message) -> list[dict[str, Any]]:
        if message.author is Author.SYSTEM:
            return []
        payload = message.payload or {}
        if payload.get("template"):
            return [dict(payload["template"])]
        slots = payload.get("slots")
        if slots:
            return [
                buttons_body(
                    message.text,
                    [(slot["id"], slot.get("short_label") or slot["label"]) for slot in slots],
                )
            ]
        bodies = text_bodies(message.text)
        cards = payload.get("cards") or []
        for card in cards:
            link = card["link"]
            if card.get("is_sample"):
                link = urljoin(self._panel_url, link.lstrip("/"))
            text = {"body": card_text(card, link), "preview_url": True}
            bodies.append({"type": "text", "text": text})
        if cards:
            bodies.append(pick_body(cards))
        return bodies
