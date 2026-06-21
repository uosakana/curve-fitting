from __future__ import annotations

from typing import Any

from app.local_assistant import answer_local_assistant


def assistant_chat_response(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not result:
        raise ValueError("Assistant payload must include a fitting result.")
    question = str(payload.get("question") or "").strip()
    history = payload.get("history") or []
    return {"ok": True, **answer_local_assistant(question, result, history)}

