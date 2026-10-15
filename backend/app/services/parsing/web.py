import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import trafilatura

from .base import ParsedDocument, ParseError, split_markdown


def parse_url(url: str) -> ParsedDocument:
    """웹 문서 한 페이지를 가져와 제목(h1~h6) 기준으로 섹션을 나눈다.

    TODO: 같은 경로 아래 여러 페이지로 나뉜 문서 사이트 수집.
    """
    _reject_internal_address(url)
    resp = httpx.get(
        url, follow_redirects=True, timeout=30, headers={"User-Agent": "TechGuideSummarizer/0.1"}
    )
    resp.raise_for_status()
    _reject_internal_address(str(resp.url))  # 리다이렉트로 내부망에 도달하는 경우 차단

    markdown = trafilatura.extract(
        resp.text, url=url, output_format="markdown", include_tables=True, include_formatting=True
    )
    if not markdown:
        raise ParseError("페이지에서 본문을 추출하지 못했습니다.")
    metadata = trafilatura.extract_metadata(resp.text, default_url=url)
    title = metadata.title if metadata and metadata.title else url
    return ParsedDocument(title=title, page_count=None, sections=split_markdown(markdown))


def _reject_internal_address(url: str) -> None:
    """서버가 사내망·로컬 주소를 대신 요청하지 않도록 막는다 (SSRF 방지)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ParseError("http 또는 https 주소만 사용할 수 있습니다.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise ParseError(f"주소를 찾을 수 없습니다: {parsed.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ParseError("내부망 주소는 가져올 수 없습니다.")
