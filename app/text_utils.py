"""Text normalization utilities for email bodies."""

from __future__ import annotations

import html
import re


def strip_html(text: str) -> str:
    if not text:
        return ""
    no_tags = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
    no_tags = re.sub(r"<[^>]+>", " ", no_tags)
    return html.unescape(re.sub(r"\s+", " ", no_tags)).strip()


def looks_like_html(text: str) -> bool:
    return bool(text and re.search(r"<(html|body|div|p|table|span|br)\b", text, re.I))


def normalize_body(text: str) -> str:
    if looks_like_html(text):
        return strip_html(text)
    return text.strip()
