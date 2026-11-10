"""Line-by-line parsing of a pasted proxy list.

Each line yields either a valid proxy URL or a rejection reason code (not translated
text, so the interface can show it in the user's language).
"""

from dataclasses import dataclass

ALLOWED_SCHEMES = ("http", "https", "socks5", "socks5h")
MAX_URL_LENGTH = 500
MAX_LINES = 1000
MAX_BYTES = 100 * 1024


@dataclass(frozen=True)
class ParsedLine:
    """Result for one line.

    Attributes:
        line: Line number, from 1.
        url: Normalized URL, or ``None``.
        reason: Rejection code, or ``None``.
    """

    line: int
    url: str | None = None
    reason: str | None = None


def _reject(line: int, reason: str) -> ParsedLine:
    return ParsedLine(line=line, reason=reason)


def _split_host_port(rest: str) -> tuple[str, str, list[str]] | str:
    """Split host, port and extra fields; return an error code when that is not possible."""
    if rest.startswith("["):
        close = rest.find("]")
        if close == -1:
            return "unclosed_ipv6"
        host, after = rest[1:close], rest[close + 1 :]
        if not after.startswith(":"):
            return "missing_port"
        parts = after[1:].split(":")
        return host, parts[0], parts[1:]
    parts = rest.split(":")
    if len(parts) < 2:
        return "missing_port"
    return parts[0], parts[1], parts[2:]


def parse_line(raw: str, line: int, default_scheme: str) -> ParsedLine:
    """Validates a line; returns its URL.

    Args:
        raw: Line text, already trimmed.
        line: Line number for the result.
        default_scheme: Scheme for lines without one.

    Returns:
    """
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return _reject(line, "invalid_characters")

    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        scheme = scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            return _reject(line, "scheme_not_allowed")
    else:
        scheme, rest = default_scheme, raw

    if any(char in rest for char in "/?#"):
        return _reject(line, "path_query_or_fragment")

    userinfo = None
    if "@" in rest:
        userinfo, rest = rest.rsplit("@", 1)
        if ":" not in userinfo:
            return _reject(line, "missing_password")
        if not userinfo.split(":", 1)[0]:
            return _reject(line, "missing_user")

    split = _split_host_port(rest)
    if isinstance(split, str):
        return _reject(line, split)
    host, port, extra = split

    if userinfo is None and extra:
        if len(extra) < 2 or not extra[0] or not extra[1]:
            return _reject(line, "missing_password")
        userinfo = f"{extra[0]}:{':'.join(extra[1:])}"
    elif userinfo is not None and extra:
        return _reject(line, "invalid_format")

    if not host:
        return _reject(line, "missing_host")
    if not port:
        return _reject(line, "missing_port")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        return _reject(line, "invalid_port")

    netloc = f"[{host}]" if ":" in host else host
    url = f"{scheme}://{userinfo + '@' if userinfo else ''}{netloc}:{int(port)}"
    if len(url) > MAX_URL_LENGTH:
        return _reject(line, "too_long")
    return ParsedLine(line=line, url=url)


def parse_text(text: str, default_scheme: str) -> list[ParsedLine]:
    """Parses every useful line of the list.

    Blank lines and lines starting with ``#`` are skipped.
    """
    results: list[ParsedLine] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        results.append(parse_line(stripped, number, default_scheme))
    return results
