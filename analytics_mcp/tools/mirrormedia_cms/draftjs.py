"""Draft.js Rich Text Converter and Editor Utilities for Mirror Media CMS."""

import re
import html
import base64
import os
from typing import Any, Dict, List, Optional


def _random_key(length: int = 5) -> str:
    """Generates a random URL-safe key for Draft.js block keys."""
    return base64.urlsafe_b64encode(os.urandom(length)).decode('utf-8').rstrip('=')[:length]


def markdown_to_html(md: str) -> str:
    """Converts basic Markdown syntax into HTML strings."""
    # Bold & Italic
    md = re.sub(r'\*\*\*(.*?)\*\*\*', r'<b><i>\1</i></b>', md)
    md = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', md)
    md = re.sub(r'\*(.*?)\*', r'<i>\1</i>', md)
    md = re.sub(r'___(.*?)___', r'<b><i>\1</i></b>', md)
    md = re.sub(r'__(.*?)__', r'<b>\1</b>', md)
    md = re.sub(r'_(.*?)_', r'<i>\1</i>', md)
    # Inline links [text](url)
    md = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', md)
    return md


def convert_to_draftjs(source: str, fmt: str = "html") -> Dict[str, Any]:
    """Converts HTML, Markdown, or plain text into Draft.js Raw Content State JSON format.
    
    Args:
        source: Input text content (HTML string, Markdown, or plain text).
        fmt: Format ('html', 'markdown', or 'plain_text').
        
    Returns:
        Dict representing Draft.js Raw Content State: {"blocks": [...], "entityMap": {...}}
    """
    if not source:
        return {
            "blocks": [{
                "key": _random_key(),
                "text": "",
                "type": "unstyled",
                "depth": 0,
                "inlineStyleRanges": [],
                "entityRanges": [],
                "data": {}
            }],
            "entityMap": {}
        }

    entity_map: Dict[str, Dict[str, Any]] = {}
    blocks: List[Dict[str, Any]] = []

    if fmt == "plain_text":
        paragraphs = [p.strip() for p in source.split("\n\n") if p.strip()]
        for p in paragraphs:
            blocks.append({
                "key": _random_key(),
                "text": p,
                "type": "unstyled",
                "depth": 0,
                "inlineStyleRanges": [],
                "entityRanges": [],
                "data": {}
            })
    else:
        # Normalize Markdown to HTML if needed
        text_source = markdown_to_html(source) if fmt == "markdown" else source
        
        # Extract paragraphs/lines
        lines = [line.strip() for line in re.split(r'</?(?:p|div|h[1-6]|li|blockquote)[^>]*>', text_source) if line.strip()]
        
        for index, line in enumerate(lines):
            clean_text = re.sub(r'<[^>]+>', '', line)
            clean_text = html.unescape(clean_text)
            
            block_type = "unstyled"
            if line.startswith("# ") or "<h1" in line.lower():
                block_type = "header-one"
            elif line.startswith("## ") or "<h2" in line.lower():
                block_type = "header-two"
            elif line.startswith("### ") or "<h3" in line.lower():
                block_type = "header-three"
            elif line.startswith("- ") or line.startswith("* ") or "<li" in line.lower():
                block_type = "unordered-list-item"
            elif line.startswith("> ") or "<blockquote" in line.lower():
                block_type = "blockquote"

            inline_styles: List[Dict[str, Any]] = []
            entity_ranges: List[Dict[str, Any]] = []

            # Check bold & italic inline ranges
            if "<b>" in line or "<strong>" in line:
                inline_styles.append({"offset": 0, "length": len(clean_text), "style": "BOLD"})
            if "<i>" in line or "<em>" in line:
                inline_styles.append({"offset": 0, "length": len(clean_text), "style": "ITALIC"})

            # Check links <a href="url">text</a>
            link_match = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', line, re.IGNORECASE)
            if link_match:
                url_href, link_text = link_match.group(1), link_match.group(2)
                entity_key = str(len(entity_map))
                entity_map[entity_key] = {
                    "type": "LINK",
                    "mutability": "MUTABLE",
                    "data": {"url": url_href}
                }
                entity_ranges.append({"offset": 0, "length": len(clean_text), "key": int(entity_key)})

            blocks.append({
                "key": _random_key(),
                "text": clean_text,
                "type": block_type,
                "depth": 0,
                "inlineStyleRanges": inline_styles,
                "entityRanges": entity_ranges,
                "data": {}
            })

    if not blocks:
        blocks.append({
            "key": _random_key(),
            "text": "",
            "type": "unstyled",
            "depth": 0,
            "inlineStyleRanges": [],
            "entityRanges": [],
            "data": {}
        })

    return {"blocks": blocks, "entityMap": entity_map}


def create_atomic_draftjs_entity(entity_type: str, data: Dict[str, Any], entity_map: Dict[str, Any]) -> Dict[str, Any]:
    """Creates a single atomic block (e.g. image, video, embed) in Draft.js shape."""
    entity_key = len(entity_map)
    entity_map[str(entity_key)] = {
        "type": entity_type,
        "mutability": "IMMUTABLE",
        "data": data
    }

    return {
        "block": {
            "key": _random_key(),
            "text": " ",
            "type": "atomic",
            "depth": 0,
            "inlineStyleRanges": [],
            "entityRanges": [{"offset": 0, "length": 1, "key": entity_key}],
            "data": {}
        },
        "entityKey": entity_key
    }
