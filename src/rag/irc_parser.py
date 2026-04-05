from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Set

from bs4 import BeautifulSoup, Tag


def _canonical_url(soup: BeautifulSoup) -> Optional[str]:
    for link in soup.find_all("link"):
        rel = link.get("rel")
        if not rel:
            continue
        parts = rel if isinstance(rel, list) else [rel]
        if any(str(r).lower() == "canonical" for r in parts):
            href = link.get("href")
            if href:
                return str(href).strip()
    return None


@dataclass
class IRCNode:
    """One retrievable unit from Cornell LII IRC HTML."""

    citation: str
    text: str
    section: str
    subsection: Optional[str] = None
    path_labels: str = ""
    source_url: Optional[str] = None

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
    if source_url is None:
        source_url = _canonical_url(soup)
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
                    source_url=source_url,
                )
            )
            dfs(child, new_vals, new_heads)

    dfs(section_root, [], [])
    return chunks


def load_irc_nodes(path: Path) -> List[IRCNode]:
    html = path.read_text(encoding="utf-8", errors="replace")
    return parse_lii_irc_html(html, source_url=None)


def load_irc_nodes_from_dir(irc_dir: Path) -> List[IRCNode]:
    """Load all `26_usc_*.html` in directory (excludes *sample*)."""
    if not irc_dir.is_dir():
        return []
    paths = sorted(
        p
        for p in irc_dir.glob("26_usc_*.html")
        if "sample" not in p.name.lower()
    )
    if not paths:
        fallback = irc_dir / "26_usc_1.html"
        if fallback.exists():
            paths = [fallback]
    all_nodes: List[IRCNode] = []
    for p in paths:
        all_nodes.extend(load_irc_nodes(p))
    return all_nodes


def _normalize_section_hints(hints: Optional[Sequence[str]]) -> Set[str]:
    if not hints:
        return set()
    out: Set[str] = set()
    for h in hints:
        if h is None:
            continue
        s = str(h).strip().lstrip("§").strip()
        if s:
            out.add(s)
    return out


def _ordered_section_hints(hints: Optional[Sequence[str]]) -> List[str]:
    """Preserve caller order (planner priors): earlier sections get a stronger rank bump."""
    seen: Set[str] = set()
    out: List[str] = []
    for h in hints or []:
        if h is None:
            continue
        s = str(h).strip().lstrip("§").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def search_irc(
    nodes: List[IRCNode],
    query: str,
    top_k: int,
    *,
    irc_sections_hint: Optional[Sequence[str]] = None,
    section_prior_boost: float = 1.55,
) -> List[tuple[float, IRCNode]]:
    """BM25 over flattened IRC chunks + heading/citation boost + optional section priors."""
    from .bm25_rank import BM25Ranker, apply_title_trail_boost

    if not nodes:
        return []
    docs = [
        f"{n.citation} {n.path_labels} {n.text} irc section {n.section}" for n in nodes
    ]
    ranker = BM25Ranker(docs)
    pool = max(top_k * 4, top_k + 8)
    hits = ranker.search(query, min(pool, len(nodes)))
    labels = [n.path_labels for n in nodes]
    cites = [n.citation for n in nodes]
    hits = apply_title_trail_boost(query, hits, labels, cites, boost=1.45)

    wanted = _normalize_section_hints(irc_sections_hint)
    ordered = _ordered_section_hints(irc_sections_hint)
    adjusted: List[tuple[int, float]] = []
    for i, sc in hits:
        mult = 1.0
        sec = nodes[i].section
        if wanted and sec in wanted and ordered:
            pos = ordered.index(sec)
            spread = max(len(ordered) - 1, 1)
            tier = (len(ordered) - 1 - pos) / spread
            mult = section_prior_boost * (1.0 + 0.35 * tier)
        elif wanted and sec in wanted:
            mult = section_prior_boost
        adjusted.append((i, sc * mult))
    adjusted.sort(key=lambda t: t[1], reverse=True)

    out: List[tuple[float, IRCNode]] = []
    seen: set[int] = set()
    for i, sc in adjusted:
        if i in seen:
            continue
        seen.add(i)
        out.append((sc, nodes[i]))
        if len(out) >= top_k:
            break
    return out
