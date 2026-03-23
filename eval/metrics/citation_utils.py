"""
Shared helpers for citation normalization, text processing, and matching.
Used by both citation_nli.py and the harness's citation existence scoring.
"""
import re


# -- Regex constants -----------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_LIST_ITEM_RE = re.compile(r"^\s*(\d+\.|[-*])\s+")
_NUMBER_ONLY_RE = re.compile(r"^\s*\d+\.\s*$")
_BRACKETED_CITATION_RE = re.compile(r"\[[^\]]+\]")
_PARENTHETICAL_CITATION_RE = re.compile(
    r"\((?:[^)]*\b(?:usc|u\.s\.c\.|irc|pub|publication|section|sec\.)\b[^)]*)\)",
    re.IGNORECASE,
)

# Common legal abbreviations that should not trigger sentence splits.
ABBREV_PROTECT = [
    "Pub.", "pub.", "Sec.", "sec.", "No.", "no.", "Rev.", "rev.",
    "Rul.", "rul.", "Proc.", "proc.", "Reg.", "reg.", "Treas.",
    "treas.", "Corp.", "corp.", "Inc.", "inc.", "Ltd.", "ltd.",
    "U.S.C.", "u.s.c.", "U.S.", "u.s.", "I.R.C.", "i.r.c.",
    "e.g.", "i.e.", "etc.", "vs.", "v.", "Ch.", "ch.", "Art.", "art.",
]


# -- Citation normalization ----------------------------------------------------

def normalize_citation_text(text: str) -> str:
    """Collapse common citation variants into a comparable form."""
    normalized = text.lower()
    normalized = normalized.replace("\u00c2\u00a7", " section ")
    normalized = normalized.replace("\u00a7", " section ")
    normalized = re.sub(r"\bi\s*\.?\s*r\s*\.?\s*c\s*\.?\b", " irc ", normalized)
    normalized = re.sub(r"\b26\s+u\s*\.?\s*s\s*\.?\s*c\s*\.?\b", " irc ", normalized)
    normalized = re.sub(r"\bsec(?:tion)?\.?\b", " section ", normalized)
    normalized = re.sub(r"\birs\s+publications?\b", " pub ", normalized)
    normalized = re.sub(r"\birs\s+pub(?:lication)?s?\.?\b", " pub ", normalized)
    normalized = re.sub(r"\bpub(?:lication)?s?\.?\b", " pub ", normalized)
    normalized = re.sub(r"\bsection\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def citation_in_text(text: str, citation: str) -> bool:
    """Check whether a citation appears in text after normalization."""
    citation_norm = normalize_citation_text(citation)
    if not citation_norm:
        return False
    return citation_norm in normalize_citation_text(text)


def find_citations_in_sentence(sentence: str, citations: list[str]) -> list[str]:
    """Find which required citations are explicitly referenced in a sentence."""
    sentence_norm = normalize_citation_text(sentence)
    return [c for c in citations if normalize_citation_text(c) in sentence_norm]


# -- Whitespace helpers --------------------------------------------------------

def normalize_space(text: str) -> str:
    """Collapse all whitespace to single spaces."""
    return _WHITESPACE_RE.sub(" ", text.strip())


# -- Abbreviation-aware sentence splitting -------------------------------------

def _protect_abbreviations(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Temporarily replace periods in abbreviations with placeholders."""
    protected = text
    replacements = []
    for abbrev in sorted(ABBREV_PROTECT, key=len, reverse=True):
        placeholder = abbrev.replace(".", "\x00")
        if abbrev in protected:
            protected = protected.replace(abbrev, placeholder)
            replacements.append((placeholder, abbrev))
    return protected, replacements


def _restore_abbreviations(text: str, replacements: list[tuple[str, str]]) -> str:
    """Restore protected abbreviations after sentence splitting."""
    restored = text
    for placeholder, original in replacements:
        restored = restored.replace(placeholder, original)
    return restored


def split_prose_paragraph(paragraph: str) -> list[str]:
    """Split a prose paragraph into sentences while protecting abbreviations."""
    protected, replacements = _protect_abbreviations(paragraph)
    candidates = re.split(r"(?<=[.!?])\s+", protected.strip())
    sentences = []
    for candidate in candidates:
        sentence = _restore_abbreviations(candidate, replacements).strip()
        if sentence and not _NUMBER_ONLY_RE.fullmatch(sentence):
            sentences.append(sentence)
    return sentences


def split_list_paragraph(paragraph: str) -> list[str]:
    """Split a numbered list paragraph into individual list items."""
    candidates = re.split(r"(?m)(?=^\s*\d+\.\s+)", paragraph.strip())
    items = []
    for candidate in candidates:
        item = candidate.strip()
        if not item:
            continue
        if _LIST_ITEM_RE.match(item):
            items.append(item)
        else:
            items.extend(split_prose_paragraph(item))
    return items


def is_list_item(text: str) -> bool:
    """Check if text starts with a list marker (e.g. '1.', '-', '*')."""
    return bool(_LIST_ITEM_RE.match(text))


# -- Hypothesis cleaning for NLI ----------------------------------------------

def clean_hypothesis(sentence: str) -> str:
    """Strip citation scaffolding and formatting noise before NLI."""
    cleaned = sentence.replace("\r", " ").replace("\n", " ")
    cleaned = _BRACKETED_CITATION_RE.sub("", cleaned)
    cleaned = _PARENTHETICAL_CITATION_RE.sub("", cleaned)
    cleaned = re.sub(r"^\s*\d+\.\s*", "", cleaned)
    cleaned = re.sub(r"[*_`]+", "", cleaned)
    cleaned = re.sub(r"^\s*according to\s+[^,]+,\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*under\s+[^,]+,\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r",?\s*as (?:provided|outlined|described|specified|stated) in\b.*$",
        "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = normalize_space(cleaned).strip(" .:;-")
    return cleaned


# -- Claim classification -----------------------------------------------------

def is_substantive_claim(cleaned_sentence: str) -> bool:
    """Return True for sentences substantial enough to score for recall."""
    if not cleaned_sentence:
        return False
    if len(cleaned_sentence) < 8:
        return False
    if not re.search(r"[A-Za-z]", cleaned_sentence):
        return False
    return True


def is_citation_only(sentence: str, citations: list[str]) -> bool:
    """Return True when the sentence is only citation scaffolding, not a claim."""
    explicit_citations = find_citations_in_sentence(sentence, citations)
    if not explicit_citations:
        return False
    stripped = sentence
    for citation in explicit_citations:
        stripped = re.sub(re.escape(citation), " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"[\[\]()]", " ", stripped)
    stripped = re.sub(
        r"^\s*(according to|see|under|source|citation)\b[:\s]*",
        "", stripped, flags=re.IGNORECASE,
    )
    stripped = re.sub(r"\s+", " ", stripped).strip(" .:;-")
    return not is_substantive_claim(stripped)
