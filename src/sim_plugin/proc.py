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
