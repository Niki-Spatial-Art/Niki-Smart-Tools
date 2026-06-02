"""Public web page fetcher with an optional Scrapling backend.

This connector is for public documentation, GitHub project pages, and article
metadata used in learning intake. It intentionally avoids stealth/bypass
features, broker sessions, paid data, and private/internal URLs.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import time
import urllib.parse
import urllib.robotparser
from dataclasses import asdict, dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup


DEFAULT_USER_AGENT = "Niki-Smart-Tools public-web-fetcher/1.0"
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


@dataclass
class PublicPage:
    url: str
    final_url: str
    title: str
    text: str
    links: list[str]
    backend: str
    status_code: int | None = None
    robots_allowed: bool | None = None


class PublicFetchError(RuntimeError):
    """Raised when a public page cannot be fetched safely."""


def _hostname(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise PublicFetchError("Only http/https URLs are supported.")
    if not parsed.hostname:
        raise PublicFetchError("URL is missing a hostname.")
    return parsed.hostname.lower()


def _is_private_host(hostname: str) -> bool:
    if hostname in BLOCKED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    return False


def validate_public_url(url: str, allow_private: bool = False) -> str:
    hostname = _hostname(url)
    if not allow_private and _is_private_host(hostname):
        raise PublicFetchError("Private, loopback, and link-local hosts are blocked.")
    return url


def robots_allowed(url: str, user_agent: str = DEFAULT_USER_AGENT, timeout: int = 6) -> bool:
    parsed = urllib.parse.urlparse(url)
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=timeout)
        if response.status_code >= 400:
            return True
        parser.parse(response.text.splitlines())
        return parser.can_fetch(user_agent, url)
    except requests.RequestException:
        return True


def _clean_text(html: str, max_chars: int) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "lxml")
    title = " ".join((soup.title.string or "").split()) if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())[:max_chars]
    links: list[str] = []
    for link in soup.find_all("a", href=True):
        href = str(link.get("href", "")).strip()
        if href and href not in links:
            links.append(href)
        if len(links) >= 30:
            break
    return title, text, links


def _html_from_scrapling_page(page: object) -> str:
    for attr in ("html", "body", "content", "text"):
        value = getattr(page, attr, None)
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            return value
    return str(page)


def fetch_with_scrapling(url: str, timeout: int, max_chars: int, user_agent: str) -> PublicPage:
    try:
        from scrapling.fetchers import Fetcher  # type: ignore
    except ImportError as exc:
        raise PublicFetchError("Scrapling is not installed. Run: pip install scrapling") from exc

    page = Fetcher.fetch(url, timeout=timeout, headers={"User-Agent": user_agent})
    html = _html_from_scrapling_page(page)
    title, text, links = _clean_text(html, max_chars=max_chars)
    final_url = str(getattr(page, "url", url) or url)
    status_code = getattr(page, "status", None) or getattr(page, "status_code", None)
    return PublicPage(
        url=url,
        final_url=final_url,
        title=title,
        text=text,
        links=links,
        backend="scrapling",
        status_code=int(status_code) if isinstance(status_code, int) else None,
    )


def fetch_with_requests(url: str, timeout: int, max_chars: int, user_agent: str) -> PublicPage:
    response = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    response.raise_for_status()
    title, text, links = _clean_text(response.text, max_chars=max_chars)
    return PublicPage(
        url=url,
        final_url=response.url,
        title=title,
        text=text,
        links=links,
        backend="requests",
        status_code=response.status_code,
    )


def fetch_public_page(
    url: str,
    *,
    backend: str = "auto",
    timeout: int = 12,
    max_chars: int = 8000,
    user_agent: str = DEFAULT_USER_AGENT,
    respect_robots: bool = True,
    allow_private: bool = False,
    delay_seconds: float = 0.0,
) -> PublicPage:
    validate_public_url(url, allow_private=allow_private)
    allowed = robots_allowed(url, user_agent=user_agent, timeout=min(timeout, 6)) if respect_robots else True
    if not allowed:
        raise PublicFetchError("robots.txt disallows fetching this URL.")
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    if backend not in {"auto", "scrapling", "requests"}:
        raise PublicFetchError("backend must be one of: auto, scrapling, requests")
    if backend in {"auto", "scrapling"}:
        try:
            page = fetch_with_scrapling(url, timeout=timeout, max_chars=max_chars, user_agent=user_agent)
            page.robots_allowed = allowed
            return page
        except PublicFetchError:
            if backend == "scrapling":
                raise
        except Exception as exc:
            if backend == "scrapling":
                raise PublicFetchError(f"Scrapling fetch failed: {exc}") from exc

    page = fetch_with_requests(url, timeout=timeout, max_chars=max_chars, user_agent=user_agent)
    page.robots_allowed = allowed
    return page


def pages_to_json(pages: Iterable[PublicPage]) -> str:
    return json.dumps([asdict(page) for page in pages], ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public pages for learning intake")
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--backend", choices=["auto", "scrapling", "requests"], default="auto")
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--ignore-robots", action="store_true")
    parser.add_argument("--allow-private", action="store_true")
    args = parser.parse_args()

    pages = [
        fetch_public_page(
            url,
            backend=args.backend,
            timeout=args.timeout,
            max_chars=args.max_chars,
            respect_robots=not args.ignore_robots,
            allow_private=args.allow_private,
        )
        for url in args.urls
    ]
    print(pages_to_json(pages))


if __name__ == "__main__":
    main()
