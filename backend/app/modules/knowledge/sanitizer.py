from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.api.errors import ApiError

ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
VOID_TAGS = {"br", "hr"}
DROP_CONTENT_TAGS = {"applet", "iframe", "math", "object", "script", "style", "svg", "template"}
BLOCK_TAGS = {
    "blockquote",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "table",
    "tr",
    "ul",
}
TEXT_BOUNDARY_TAGS = BLOCK_TAGS | {"a"}


def _safe_href(value: str) -> str | None:
    candidate = "".join(character for character in value.strip() if ord(character) >= 32)
    if not candidate:
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() in {"http", "https", "mailto", "tel"}:
        return candidate
    if not parsed.scheme and (
        candidate.startswith("#") or (candidate.startswith("/") and not candidate.startswith("//"))
    ):
        return candidate
    return None


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.suppressed_depth:
            self.suppressed_depth += 1
            return
        if tag in DROP_CONTENT_TAGS:
            self.suppressed_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return
        allowed: list[tuple[str, str]] = []
        attributes = {name.lower(): value for name, value in attrs if value is not None}
        if tag == "a":
            href = _safe_href(attributes.get("href", ""))
            if href is not None:
                allowed.append(("href", href))
                title = attributes.get("title", "").strip()
                if title:
                    allowed.append(("title", title[:500]))
                if attributes.get("target") == "_blank":
                    allowed.extend((("target", "_blank"), ("rel", "noopener noreferrer")))
        if tag in {"td", "th"}:
            for name in ("colspan", "rowspan"):
                value = attributes.get(name, "")
                if value.isdigit() and 1 <= int(value) <= 20:
                    allowed.append((name, value))
        rendered = "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in allowed)
        self.output.append(f"<{tag}{rendered}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if self.suppressed_depth or normalized in DROP_CONTENT_TAGS:
            return
        self.handle_starttag(tag, attrs)
        if normalized in ALLOWED_TAGS and normalized not in VOID_TAGS:
            self.output.append(f"</{normalized}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.suppressed_depth:
            self.suppressed_depth -= 1
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.suppressed_depth:
            self.output.append(html.escape(data, quote=False))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in TEXT_BOUNDARY_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in TEXT_BOUNDARY_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def sanitize_knowledge_html(raw_html: str) -> tuple[str, str]:
    sanitizer = _Sanitizer()
    sanitizer.feed(raw_html)
    sanitizer.close()
    sanitized = "".join(sanitizer.output)
    extractor = _TextExtractor()
    extractor.feed(sanitized)
    extractor.close()
    plain_text = re.sub(r"\s+", " ", "".join(extractor.parts)).strip()
    if not plain_text:
        raise ApiError(422, "empty_content", "Knowledge content must contain readable text")
    return sanitized, plain_text
