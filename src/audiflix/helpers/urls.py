"""Server-URL validation and same-origin checks.

Two independent concerns live here, both security relevant:

1. :func:`normalize_server_url` turns whatever the user typed into a clean,
   canonical base URL (``https://host[:port][/subpath]``) or explains what is
   wrong with it. :func:`is_plain_http` lets the UI warn loudly before
   credentials are sent over an unencrypted connection.
2. :func:`is_same_origin` decides whether an auth token may be attached to a
   URL. Audiobookshelf can hand out absolute media URLs; sending our bearer
   token to a third-party host or CDN would leak the user's account.

The module deliberately has no wx or requests dependency so it can be unit
tested on any platform.
"""

from __future__ import annotations

from urllib.parse import quote, urlparse, urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidServerUrl(ValueError):
    """The user supplied a URL that cannot be used as an Audiobookshelf host."""


def normalize_server_url(raw: str) -> str:
    """Validate and canonicalise a server URL.

    ``abs.example.com`` becomes ``https://abs.example.com``; a trailing slash
    and an explicit default port are removed; the path is kept because
    Audiobookshelf is often hosted under a sub-path (``/audiobookshelf``).

    Raises :class:`InvalidServerUrl` with a message meant for the user.
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidServerUrl("empty")

    # A bare host or "host:8080" has no scheme - default to HTTPS.
    if "://" not in text:
        text = "https://" + text

    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidServerUrl("scheme")
    if not parts.hostname:
        raise InvalidServerUrl("host")
    if parts.query or parts.fragment:
        raise InvalidServerUrl("extra")

    try:
        port = parts.port
    except ValueError as exc:  # non-numeric or out-of-range port
        raise InvalidServerUrl("port") from exc

    host = parts.hostname
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    netloc = host if port is None or port == DEFAULT_PORTS[scheme] else f"{host}:{port}"

    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def is_plain_http(url: str) -> bool:
    """True when ``url`` uses unencrypted HTTP (credentials would be readable)."""
    return urlparse(url).scheme.lower() == "http"


def is_loopback(url: str) -> bool:
    """True for localhost / 127.0.0.0/8 / ::1 - plain HTTP is acceptable there."""
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "::1") or host.startswith("127.")


def origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port) with the default port normalised away."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is not None and port == DEFAULT_PORTS.get(scheme):
        port = None
    return scheme, host, port


def is_same_origin(base_url: str, other_url: str) -> bool:
    """True when ``other_url`` points at the same scheme/host/port as ``base_url``.

    Relative URLs (no scheme and no host) are treated as same-origin because
    they are resolved against ``base_url``.
    """
    parts = urlsplit(other_url)
    if not parts.scheme and not parts.netloc:
        return True
    return origin(base_url) == origin(other_url)


def join_base(base_url: str, relative_url: str) -> str:
    """Append a server-relative path to the configured base URL."""
    if not relative_url.startswith("/"):
        relative_url = "/" + relative_url
    return f"{base_url.rstrip('/')}{relative_url}"


def with_token(url: str, token: str) -> str:
    """Append ``?token=`` / ``&token=`` to ``url``.

    Callers must have checked :func:`is_same_origin` first - this function does
    not decide *whether* a token may be attached, only how.
    """
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}token={quote(token, safe='')}"


def redact_token(url: str) -> str:
    """Replace the ``token`` query value so a URL can safely be logged."""
    from audiflix.logging_setup import redact

    return redact(url)
