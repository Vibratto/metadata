"""``logging`` filters: current job and sensitive data."""

import logging
import re
from contextvars import ContextVar
from typing import Any

# ``contextvars`` rather than a global: each worker thread keeps its own id.
current_job_id: ContextVar[str] = ContextVar("current_job_id", default="-")

_SENSITIVE = (
    r"passw\w*|token\w*|cookie|set-cookie|sessionid|csrf\w*|secret\w*|authorization|api[_-]?key"
)
_KEY_RE = re.compile(rf"(?i)^(?:{_SENSITIVE})$")
# ``key=value``, ``key: value`` and ``"key": "value"`` inside free text.
_TEXT_RE = re.compile(rf"""(?ix)((?:{_SENSITIVE})["']?\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&]+)""")
# ``scheme://user:pass@host``: proxy credentials travel in the URL.
_URL_USERINFO_RE = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@]+@")
REDACTED = "***"


def redact(value: Any) -> Any:
    """Hides passwords, tokens and cookies from a value.

    Args:
        value: Text, dict or list (nested).

    Returns:
        A copy with sensitive values replaced by ``***``.
    """
    if isinstance(value, dict):
        return {
            k: REDACTED if isinstance(k, str) and _KEY_RE.match(k) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _TEXT_RE.sub(rf"\g<1>{REDACTED}", _URL_USERINFO_RE.sub(rf"\g<1>{REDACTED}@", value))
    return value


class JobIdFilter(logging.Filter):
    """Adds ``job_id`` to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Annotates the record and lets it through."""
        record.job_id = current_job_id.get()
        return True


class SensitiveDataFilter(logging.Filter):
    """Hides sensitive data before the record reaches a handler. The message is
    formatted here so secrets passed as ``%s`` arguments are caught too.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Swaps in the cleaned message."""
        record.msg = redact(record.getMessage())
        record.args = None
        return True
