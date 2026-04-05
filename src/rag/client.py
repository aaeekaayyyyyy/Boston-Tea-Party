from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.planning.contracts import (
    RetrievalChunk,
    RetrievalChunkMetadata,
    RetrievalResponse,
)

from .irc_parser import load_irc_nodes, load_irc_nodes_from_dir, search_irc
from .irs_pageindex import IRSPublicationRetriever
from .tax_court_bm25 import TaxCourtBM25Index

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_repo_dotenv() -> None:
    """Load KEY=value lines from repo .env if present (does not override existing env)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _infer_auto_sources(query: str) -> List[str]:
    q = query.lower()
    if any(
        w in q
        for w in (
            "tax court",
            "opinion",
            "commissioner",
            "docket",
            "judicial",
            "petitioner",
        )
    ):
        return ["tax_court"]
    if any(
        w in q
        for w in (
            "26 u.s.c",
            "usc §",
            "irc ",
            "internal revenue code",
            "statute",
            "subsection (",
        )
    ):
        return ["irc"]
    return ["irs_pubs", "irc"]


class HybridRetrievalClient:
    """
    Hybrid retrieval implementing RetrievalClientProtocol:
    - irs_pubs: PageIndex tree (cache or API) + tax metadata
    - irc: Cornell LII HTML parser + 26 USC § citations
    - tax_court: BM25 over JSONL corpus
    - source_hint None: heuristic multi-source (irs + irc, or tax_court if query suggests case law)
    """

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        *,
        irc_html_path: Optional[Path] = None,
        irc_dir: Optional[Path] = None,
        irs_pdf_path: Optional[Path] = None,
        irs_publication: str = "501",
        irs_publication_year: int = 2025,
        pageindex_cache_path: Optional[Path] = None,
        tax_court_corpus_path: Optional[Path] = None,
    ) -> None:
        _load_repo_dotenv()
        self.repo_root = repo_root or REPO_ROOT
        self._irc_explicit = irc_html_path
        self._irc_dir = irc_dir or (self.repo_root / "sources" / "irc")
        self._irs_pdf = irs_pdf_path or (self.repo_root / "sources" / "irs_pubs" / "p501_sample.pdf")
        self._irs_publication = irs_publication
        self._irs_year_default = irs_publication_year
        cache = pageindex_cache_path or (self.repo_root / "data" / "rag" / "pageindex_irs_tree.json")
        self._irs = IRSPublicationRetriever(
            publication=irs_publication,
            publication_year=irs_publication_year,
            pdf_path=self._irs_pdf if self._irs_pdf.exists() else None,
            cache_path=cache,
            doc_id=os.environ.get("PAGEINDEX_IRS_DOC_ID"),
        )
        tc_path = tax_court_corpus_path or (
            self.repo_root / "data" / "rag" / "tax_court_corpus.jsonl"
        )
        self._tax_court = TaxCourtBM25Index(tc_path)
        self._irc_nodes: Optional[list] = None

    def _irc_nodes_cached(self):
        if self._irc_nodes is None:
            if self._irc_explicit is not None:
                self._irc_nodes = (
                    load_irc_nodes(self._irc_explicit)
                    if self._irc_explicit.exists()
                    else []
                )
            else:
                self._irc_nodes = load_irc_nodes_from_dir(self._irc_dir)
        return self._irc_nodes

    def _apply_tax_year(self, options: Optional[Dict[str, Any]]) -> None:
        opts = options or {}
        y = opts.get("tax_year")
        if y is not None:
            try:
                self._irs.publication_year = int(y)
            except (TypeError, ValueError):
                pass
        else:
            self._irs.publication_year = self._irs_year_default

    def _retrieve_irs(
        self, query: str, top_k: int, options: Optional[Dict[str, Any]]
    ) -> RetrievalResponse:
        prev_pub = self._irs.publication
        prev_year = self._irs.publication_year
        try:
            self._apply_tax_year(options)
            pub = (options or {}).get("irs_publication")
            if pub:
                self._irs.publication = str(pub)
            else:
                self._irs.publication = self._irs_publication

            flat = self._irs.ensure_flat()
            if not flat:
                return RetrievalResponse(
                    chunks=[],
                    strategy="tree",
                    sources_queried=["irs_pubs"],
                    retrieval_message=(
                        "IRS publication tree is empty: refresh data/rag/pageindex_irs_tree.json "
                        "or configure PAGEINDEX_API_KEY / PAGEINDEX_IRS_DOC_ID."
                    ),
                )

            scored = self._irs.search(query, top_k, options)
            chunks: List[RetrievalChunk] = []
            for score, row in scored:
                trail = row.get("trail") or row.get("title") or ""
                chunks.append(
                    RetrievalChunk(
                        text=row.get("text") or row.get("title") or "",
                        metadata=RetrievalChunkMetadata(
                            source_type="irs_pubs",
                            citation=self._irs.citation_for(row),
                            section=None,
                            publication_year=self._irs.publication_year,
                            publication=str(self._irs.publication),
                            case_name=None,
                            page_index=row.get("page_index"),
                            heading_trail=trail,
                            node_id=str(row["node_id"]) if row.get("node_id") else None,
                        ),
                        score=score,
                    )
                )
            return RetrievalResponse(
                chunks=chunks,
                strategy="tree",
                sources_queried=["irs_pubs"],
            )
        finally:
            self._irs.publication = prev_pub
            self._irs.publication_year = prev_year

    def _retrieve_irc(
        self, query: str, top_k: int, options: Optional[Dict[str, Any]]
    ) -> RetrievalResponse:
        nodes = self._irc_nodes_cached()
        opts = options or {}
        hints = opts.get("irc_sections_hint")
        scored = search_irc(
            nodes,
            query,
            top_k,
            irc_sections_hint=hints if isinstance(hints, (list, tuple)) else None,
        )
        chunks: List[RetrievalChunk] = []
        for score, node in scored:
            chunks.append(
                RetrievalChunk(
                    text=node.text,
                    metadata=RetrievalChunkMetadata(
                        source_type="irc",
                        citation=node.citation,
                        section=node.section,
                        publication_year=None,
                        publication=None,
                        case_name=None,
                        page_index=None,
                        subsection=node.subsection,
                        heading_trail=node.path_labels or None,
                        node_id=None,
                        source_url=node.source_url,
                    ),
                    score=score,
                )
            )
        if not chunks:
            return RetrievalResponse(
                chunks=[],
                strategy="tree",
                sources_queried=["irc"],
                retrieval_message=(
                    "No IRC chunks loaded: add sources/irc/26_usc_<section>.html "
                    "(see scripts/download_irc_sections.py)."
                ),
            )
        return RetrievalResponse(
            chunks=chunks,
            strategy="tree",
            sources_queried=["irc"],
        )

    def _retrieve_tax_court(
        self, query: str, top_k: int, _options: Optional[Dict[str, Any]]
    ) -> RetrievalResponse:
        scored = self._tax_court.search(query, top_k)
        chunks: List[RetrievalChunk] = []
        for score, text, meta in scored:
            case = meta.get("case_name") or "Unknown"
            year = meta.get("year")
            dkt = meta.get("docket")
            cite = f"{case} ({year})" if year else case
            if dkt:
                cite = f"{cite}, Dkt. {dkt}"
            chunks.append(
                RetrievalChunk(
                    text=text,
                    metadata=RetrievalChunkMetadata(
                        source_type="tax_court",
                        citation=cite,
                        section=None,
                        publication_year=int(year) if year is not None else None,
                        publication=None,
                        case_name=case,
                        page_index=None,
                        heading_trail=None,
                        node_id=str(meta.get("chunk_id"))
                        if meta.get("chunk_id") is not None
                        else None,
                        source_url=meta.get("source_url"),
                    ),
                    score=score,
                )
            )
        if not chunks:
            return RetrievalResponse(
                chunks=[],
                strategy="bm25",
                sources_queried=["tax_court"],
                retrieval_message="Tax Court corpus is empty or produced no BM25 hits.",
            )
        return RetrievalResponse(
            chunks=chunks,
            strategy="bm25",
            sources_queried=["tax_court"],
        )

    def _retrieve_auto(
        self, query: str, top_k: int, options: Optional[Dict[str, Any]]
    ) -> RetrievalResponse:
        sources = _infer_auto_sources(query)
        if sources == ["tax_court"]:
            return self._retrieve_tax_court(query, top_k, options)

        combined: List[RetrievalChunk] = []
        queried: List[str] = []
        if "irs_pubs" in sources:
            k = max(1, top_k // 2) if len(sources) > 1 else top_k
            r = self._retrieve_irs(query, k, options)
            combined.extend(r.chunks)
            queried.extend(r.sources_queried)
        if "irc" in sources:
            k = top_k - len(combined) if combined else top_k
            k = max(1, k)
            r = self._retrieve_irc(query, k, options)
            combined.extend(r.chunks)
            queried.extend(r.sources_queried)

        combined.sort(key=lambda c: c.score or 0.0, reverse=True)
        return RetrievalResponse(
            chunks=combined[:top_k],
            strategy="tree",
            sources_queried=list(dict.fromkeys(queried)),
        )

    def retrieve(
        self,
        query: str,
        source_hint: Optional[str] = None,
        top_k: int = 5,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if source_hint == "irs_pubs":
            resp = self._retrieve_irs(query, top_k, options)
        elif source_hint == "irc":
            resp = self._retrieve_irc(query, top_k, options)
        elif source_hint == "tax_court":
            resp = self._retrieve_tax_court(query, top_k, options)
        else:
            resp = self._retrieve_auto(query, top_k, options)
        return resp.to_dict()
