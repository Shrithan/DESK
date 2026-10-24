"""ASI:One Interactive Cards (card protocol v1).

A card is a chat-protocol ChatMessage with a TextContent narration (fallback
text) plus a MetadataContent carrying the card. When the user taps a button,
ASI:One sends the button's ``selection`` back as a chat message: JSON on a direct
@mention, or a prose sentence when routed by the ASI:One planner.

Spec: https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent

MAX_PAYLOAD_BYTES = 60_000


def cta(label: str, action: str, *, primary: bool = False, **data: Any) -> dict:
    out: dict[str, Any] = {"label": label, "selection": {"action": action, **data}}
    if primary:
        out["primary"] = True
    return out


def rows(pairs) -> list[dict]:
    return [{"label": str(k), "value": str(v)} for k, v in pairs]


def detail(title: str, pairs, ctas: list[dict]) -> tuple[str, dict]:
    return "detail", {"title": title, "summary_rows": rows(pairs), "ctas": ctas}


def info(title: str, pairs) -> tuple[str, dict]:
    return "detail", {"title": title, "summary_rows": rows(pairs), "ctas": []}


def review(title: str, pairs, approve: dict, reject: dict) -> tuple[str, dict]:
    return "review", {"title": title, "summary_rows": rows(pairs), "approve_cta": approve, "reject_cta": reject}


def form(title: str, fields: list[dict], submit: dict) -> tuple[str, dict]:
    return "form", {"title": title, "fields": fields, "submit_cta": submit}


def select_field(name: str, label: str, options: list[tuple[str, str]], required: bool = True) -> dict:
    out = {"name": name, "kind": "select", "label": label, "options": [{"value": v, "label": lab} for v, lab in options]}
    if required:
        out["required"] = True
    return out


def carousel(title: str, items: list[dict]) -> tuple[str, dict]:
    return "carousel", {"title": title, "items": items}


def item(id: str, title: str, *, action: str, cta_label: str, subtitle: str | None = None) -> dict:
    out = {"id": id, "title": title, "primary_cta": cta(cta_label, action, id=id)}
    if subtitle:
        out["subtitle"] = subtitle
    return out


def message(narration: str, card: tuple[str, dict] | None = None, *, terminal: bool = False) -> ChatMessage:
    content: list[Any] = [TextContent(type="text", text=narration)]
    if card is not None:
        kind, payload = card
        body = json.dumps(payload, ensure_ascii=False)
        if len(body.encode()) > MAX_PAYLOAD_BYTES:
            raise ValueError("card payload too large")
        meta = {"card_protocol_version": "1", "requires_card_interaction": "false" if terminal else "true",
                "card_kind": kind, "card_payload": body}
        if terminal:
            meta["is_terminal"] = "true"
        content.append(MetadataContent(type="metadata", metadata=meta))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


_MENTION = re.compile(r"^(?:@\S+\s+)+")


def strip_mention(text: str) -> str:
    return _MENTION.sub("", (text or "").strip()).strip()


def parse_selection(text: str, known_actions: set[str]) -> dict:
    """Recover a card tap from an inbound message; {} for ordinary text."""
    raw = (text or "").strip()
    for candidate in (strip_mention(raw), raw):
        try:
            data = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            nested = data.get("selection")
            if not data.get("action") and isinstance(nested, dict):
                data = {**{k: v for k, v in data.items() if k != "selection"}, **nested}
            if data.get("action"):
                return data
    low = raw.lower()
    for action in sorted(known_actions, key=len, reverse=True):
        if re.search(rf"(?<![\w-]){re.escape(action)}(?![\w-])", low):
            return {"action": action, "prose": raw}
    return {}
