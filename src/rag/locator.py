from __future__ import annotations

from typing import Any, Dict


def retrieval_locator(metadata: Dict[str, Any]) -> str:
    """
    Single normalized locator string for verification tooling (Francesco).
    Avoids re-parsing citation strings when metadata is already structured.
    """
    st = (metadata.get("source_type") or "").strip()
    if st == "irs_pubs":
        parts = [
            "irs_pubs",
            metadata.get("publication") or "",
            str(metadata.get("publication_year") or ""),
            metadata.get("node_id") or "",
            metadata.get("heading_trail") or "",
        ]
        return "|".join(p for p in parts if p)
    if st == "irc":
        parts = [
            "irc",
            metadata.get("section") or "",
            metadata.get("subsection") or "",
            metadata.get("source_url") or "",
        ]
        return "|".join(p for p in parts if p)
    if st == "tax_court":
        parts = [
            "tax_court",
            metadata.get("case_name") or "",
            str(metadata.get("publication_year") or ""),
            metadata.get("citation") or "",
            metadata.get("node_id") or "",
        ]
        return "|".join(p for p in parts if p)
    return "|".join(
        p
        for p in (st, metadata.get("citation") or "", metadata.get("node_id") or "")
        if p
    )
