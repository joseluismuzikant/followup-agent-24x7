"""How the lead agent's messages look on WhatsApp (the product's `MessageRenderer`)."""

from typing import Any
from urllib.parse import urljoin

from followup_core.conversation.domain.thread import Author, Message
from followup_core.messaging.domain.outbound import buttons_body, text_bodies

OVER_BUDGET_NOTE = "Un poco más de tu presupuesto"


def card_text(card: dict[str, Any], link: str) -> str:
    lines = [f"*{card['title']}*", str(card["address"]), str(card["price_label"])]
    if card.get("over_budget"):
        lines.append(OVER_BUDGET_NOTE)
    lines.append(link)
    return "\n".join(lines)


class LeadMessageRenderer:
    """- text → text messages (split above 4,096 characters);
    - property cards → the intro text, then one message per card with the title in bold,
      address, price, the over-budget note and the listing link (with its preview);
    - visit slots → reply buttons (ids are the slot ids, titles "jue 6/11 10:30");
    - system messages (the hand-off event) → nothing: they are never sent to the lead.
    """

    def __init__(self, panel_url: str) -> None:
        # Sample listings link to the panel's /ejemplo pages, which need an absolute URL.
        self._panel_url = panel_url.rstrip("/") + "/"

    def __call__(self, message: Message) -> list[dict[str, Any]]:
        if message.author is Author.SYSTEM:
            return []
        payload = message.payload or {}
        slots = payload.get("slots")
        if slots:
            return [
                buttons_body(
                    message.text,
                    [(slot["id"], slot.get("short_label") or slot["label"]) for slot in slots],
                )
            ]
        bodies = text_bodies(message.text)
        for card in payload.get("cards") or []:
            link = card["link"]
            if card.get("is_sample"):
                link = urljoin(self._panel_url, link.lstrip("/"))
            text = {"body": card_text(card, link), "preview_url": True}
            bodies.append({"type": "text", "text": text})
        return bodies
