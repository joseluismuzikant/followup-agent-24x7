"""Reads one listing page, guarded against SSRF: the URL comes from the user.

- http/https only, on the standard ports (80/443), no credentials in the URL;
- the host is resolved here and every address must be public: private, loopback,
  link-local (169.254.169.254, the cloud metadata service), shared, reserved and multicast
  ranges are refused. The connection then goes to the address that was checked (the Host
  header and TLS SNI carry the name), so a second DNS answer cannot point elsewhere;
- the same checks on every redirect, at most 3;
- 10 s for the whole read, at most 3 MB, text/html only, our own user agent, no cookies, no
  proxies from the environment, no retries, no JavaScript. Only the URL given: no crawling.

A portal that blocks us (bot protection: 403, 429...) is reported as BLOCKED, never worked
around.
"""

import ipaddress
import logging
import re
import socket
import time
from collections.abc import Callable, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from ..domain.listing import (
    FETCH_TIMEOUT_SECONDS,
    MAX_PAGE_BYTES,
    MAX_REDIRECTS,
    USER_AGENT,
    FetchedPage,
    ListingFetchError,
    ListingUrlError,
    ReadProblem,
)

logger = logging.getLogger("inmo24x7.listing")

Resolver = Callable[[str, int], Sequence[str]]
"""host, port -> the addresses it resolves to."""

_BLOCKED_STATUSES = frozenset({401, 403, 407, 429, 451, 503})
_GONE_STATUSES = frozenset({404, 410})
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([\w-]+)""", re.IGNORECASE)


def system_resolver(host: str, port: int) -> Sequence[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as error:
        raise ListingFetchError(ReadProblem.UNREACHABLE) from error
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def checked_target(url: str, resolve: Resolver) -> tuple[str, str]:
    """(the URL to connect to, by checked address; the host name). Raises ListingUrlError."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise ListingUrlError(url) from error
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        raise ListingUrlError("scheme")
    if parts.username or parts.password:
        raise ListingUrlError("credentials")
    default = 443 if scheme == "https" else 80
    if port not in (None, default):
        raise ListingUrlError("port")
    host = parts.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ListingUrlError("host")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    addresses = [str(literal)] if literal else list(resolve(host, default))
    if not addresses or not all(is_public_address(address) for address in addresses):
        raise ListingUrlError("private_address")
    address = addresses[0]
    netloc = f"[{address}]" if ":" in address else address
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, "")), host


def _decode(content: bytes, content_type: str) -> str:
    charset = None
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=", 1)[1].split(";")[0].strip(" \"'")
    if not charset:
        found = _CHARSET.search(content[:4096])
        charset = found.group(1).decode("ascii", "ignore") if found else "utf-8"
    try:
        return content.decode(charset, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


class SafePageFetcher:
    def __init__(
        self,
        resolve: Resolver = system_resolver,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = FETCH_TIMEOUT_SECONDS,
        max_bytes: int = MAX_PAGE_BYTES,
    ) -> None:
        self._resolve = resolve
        self._transport = transport
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes

    def fetch(self, url: str) -> FetchedPage:
        deadline = time.monotonic() + self._timeout
        with httpx.Client(
            transport=self._transport,
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,  # no proxies from the environment
        ) as client:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                target, host = checked_target(current, self._resolve)
                outcome = self._get(client, target, host, current, deadline)
                if isinstance(outcome, FetchedPage):
                    return outcome
                current = outcome
            raise ListingFetchError(ReadProblem.UNREACHABLE)  # too many redirects

    def _get(
        self, client: httpx.Client, target: str, host: str, url: str, deadline: float
    ) -> FetchedPage | str:
        """The page, or the next URL to follow."""
        client.cookies.clear()  # never send what a previous hop set
        parts = urlsplit(url)
        host_header = parts.netloc.rsplit("@", 1)[-1]
        request = client.build_request(
            "GET",
            target,
            headers={
                "Host": host_header,
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-AR,es;q=0.9",
            },
            extensions={"sni_hostname": host},
        )
        try:
            response = client.send(request, stream=True)
        except httpx.TimeoutException as error:
            raise ListingFetchError(ReadProblem.TIMEOUT) from error
        except httpx.HTTPError as error:
            raise ListingFetchError(ReadProblem.UNREACHABLE) from error
        try:
            status = response.status_code
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ListingFetchError(ReadProblem.UNREACHABLE)
                return urljoin(url, location)
            if status != 200:
                logger.info("listing_fetch_refused", extra={"status": status, "host": host})
            if status in _BLOCKED_STATUSES:
                raise ListingFetchError(ReadProblem.BLOCKED)
            if status in _GONE_STATUSES:
                raise ListingFetchError(ReadProblem.GONE)
            if not 200 <= status < 300:
                raise ListingFetchError(ReadProblem.UNREACHABLE)
            content_type = response.headers.get("content-type", "")
            if not content_type.lower().startswith(_HTML_TYPES):
                raise ListingFetchError(ReadProblem.NOT_HTML)
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > self._max_bytes:
                raise ListingFetchError(ReadProblem.TOO_LARGE)
            content = bytearray()
            try:
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self._max_bytes:
                        raise ListingFetchError(ReadProblem.TOO_LARGE)
                    if time.monotonic() > deadline:
                        raise ListingFetchError(ReadProblem.TIMEOUT)
            except httpx.TimeoutException as error:
                raise ListingFetchError(ReadProblem.TIMEOUT) from error
            except httpx.HTTPError as error:
                raise ListingFetchError(ReadProblem.UNREACHABLE) from error
            return FetchedPage(url, _decode(bytes(content), content_type))
        finally:
            response.close()
