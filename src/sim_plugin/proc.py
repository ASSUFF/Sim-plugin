"""Text capture for solver subprocesses.

Native Windows tools print in the console code page. Our own Python engines
print UTF-8 JSON. Either way, a decode error must not erase the real message.
"""

from __future__ import annotations

import locale


def capture_native():
    return {
        "text": True,
        "encoding": locale.getpreferredencoding(False) or "utf-8",
        "errors": "replace",
    }


def capture_utf8():
    return {"text": True, "encoding": "utf-8", "errors": "replace"}


def log_tail(*chunks: str, limit: int = 20) -> str:
    """Keep the last lines of solver output. Empty input stays empty."""
    lines: list[str] = []
    for chunk in chunks:
        if chunk:
            lines.extend(str(chunk).splitlines())
    if not lines:
        return ""
    return "\n".join(lines[-limit:])


def attach_log_tail(payload: dict, *chunks: str) -> dict:
    if payload.get("ok") is False:
        tail = log_tail(*chunks)
        if tail:
            payload["log_tail"] = tail
    return payload
