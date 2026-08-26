"""Draft.js Rich Text Converter and Editor Utilities for Keystone CMS."""

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
    md = re.sub(r'\*\*\*(.*?)\*\*\*', r'<b><i>\1</i></b>', md)
    md = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', md)
    md = re.sub(r'\*(.*?)\*', r'<i>\1</i>', md)
    md = re.sub(r'___(.*?)___', r'<b><i>\1</i></b>', md)
    md = re.sub(r'__(.*?)__', r'<b>\1</b>', md)
    md = re.sub(r'_(.*?)_', r'<i>\1</i>', md)
    md = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', md)
    return md


def convert_to_draftjs(content: str, input_type: str = "auto") -> Dict[str, Any]:
    """Converts text, Markdown, or HTML content into Keystone 6 Draft.js raw JSON format."""
    if not content:
        draftjs_json = {
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
        return {"draftjs_json": json.dumps(draftjs_json), "raw_state": draftjs_json}

    entity_map: Dict[str, Dict[str, Any]] = {}
    blocks: List[Dict[str, Any]] = []

    # Detect input type if set to auto
    fmt = input_type
    if fmt == "auto":
        if "<" in content and ">" in content:
            fmt = "html"
        elif "# " in content or "**" in content or "]" in content:
            fmt = "markdown"
        else:
            fmt = "plain_text"

    if fmt == "plain_text":
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
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
        text_source = markdown_to_html(content) if fmt == "markdown" else content
        lines = [line.strip() for line in re.split(r'</?(?:p|div|h[1-6]|li|blockquote)[^>]*>', text_source) if line.strip()]
        
        for line in lines:
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

            if "<b>" in line or "<strong>" in line:
                inline_styles.append({"offset": 0, "length": len(clean_text), "style": "BOLD"})
            if "<i>" in line or "<em>" in line:
                inline_styles.append({"offset": 0, "length": len(clean_text), "style": "ITALIC"})

            link_match = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', line, re.IGNORECASE)
            if link_match:
                url_href = link_match.group(1)
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

    raw_state = {"blocks": blocks, "entityMap": entity_map}
    import json
    return {"draftjs_json": json.dumps(raw_state), "raw_state": raw_state}
