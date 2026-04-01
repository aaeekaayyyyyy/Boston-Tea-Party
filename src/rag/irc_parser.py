from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup, Tag


@dataclass
class IRCNode:
    """One retrievable unit from Cornell LII IRC HTML."""

    citation: str
    text: str
    section: str
    subsection: Optional[str] = None
    path_labels: str = ""

    def score_query(self, query: str) -> float:
        q = _tokenize(query)
        if not q:
            return 0.0
        blob = _tokenize(self.citation + " " + self.text + " " + self.path_labels)
        return len(q & blob) / len(q)


def _tokenize(s: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{2,}", s.lower()))


def _extract_section_number(h1_text: str) -> str:
    m = re.search(r"§\s*([0-9]+[A-Za-z]?)", h1_text.replace("\u202f", " "))
    if m:
        return m.group(1)
    m2 = re.search(r"section\s+(\d+[A-Za-z]?)", h1_text, re.I)
    return m2.group(1) if m2 else "?"


def _structural_tag(div: Tag) -> Optional[str]:
    classes = div.get("class") or []
    for name in ("subsection", "paragraph", "subparagraph", "clause"):
        if name in classes:
            return name
    return None


def _num_value(div: Tag) -> Optional[str]:
    for span in div.find_all("span", class_=True, recursive=False):
        cls = " ".join(span.get("class") or [])
        if "num" not in cls:
            continue
        v = span.get("value")
        if v:
            return str(v)
    for span in div.find_all("span", class_=True):
        cls = " ".join(span.get("class") or [])
        if "num" not in cls:
            continue
        v = span.get("value")
        if v:
            return str(v)
    return None


def _heading_text(div: Tag) -> str:
    h = div.find("span", class_=lambda c: c and "heading" in c.split())
    return h.get_text(separator=" ", strip=True) if h else ""


def parse_lii_irc_html(html: str, *, source_url: Optional[str] = None) -> List[IRCNode]:
    """
    Parse Cornell LII single-section IRC HTML into hierarchical citation nodes.
    Emits one chunk per structural unit that has a span.num[value] (subsection, paragraph, etc.).
    """
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1#page_title") or soup.select_one("h1.title")
    if not h1:
        return []
    section_num = _extract_section_number(h1.get_text())
    section_root = soup.select_one("div.text div.section") or soup.select_one("div.section")
    if not section_root or not isinstance(section_root, Tag):
        return []

    chunks: List[IRCNode] = []

    def dfs(el: Tag, path_values: List[str], path_heads: List[str]) -> None:
        for child in el.find_all(recursive=False):
            if not isinstance(child, Tag) or child.name != "div":
                continue
            tag = _structural_tag(child)
            if not tag:
                dfs(child, path_values, path_heads)
                continue
            val = _num_value(child)
            if not val:
                dfs(child, path_values, path_heads)
                continue
            new_vals = path_values + [val]
            head = _heading_text(child)
            new_heads = path_heads + [head] if head else path_heads
            cite_suffix = "".join(f"({v})" for v in new_vals)
            citation = f"26 USC § {section_num}{cite_suffix}"
            if source_url:
                citation = f"{citation} ({source_url})"
            text = child.get_text(separator=" ", strip=True)
            if len(text) < 10:
                dfs(child, new_vals, new_heads)
                continue
            chunks.append(
                IRCNode(
                    citation=citation,
                    text=text[:12000],
                    section=section_num,
                    subsection=new_vals[0] if new_vals else None,
                    path_labels=" ".join(new_heads),
                )
            )
            dfs(child, new_vals, new_heads)

    dfs(section_root, [], [])
    return chunks


def load_irc_nodes(path: Path) -> List[IRCNode]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_lii_irc_html(html, source_url=None)


def search_irc(nodes: List[IRCNode], query: str, top_k: int) -> List[tuple[float, IRCNode]]:
    scored = [(n.score_query(query), n) for n in nodes]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x for x in scored[:top_k] if x[0] > 0] or scored[:top_k]
