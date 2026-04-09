#!/usr/bin/env python3
"""
Serve the Boston Tea Party 2.0 web UI + full planning stack API.

Runs **SimpleConstraintEngine**, **PlanningAgent**, and **HybridRetrievalClient** (PageIndex IRS tree,
IRC HTML, Tax Court BM25) by default. Optional `use_mock: true` on POST /api/plan uses a small stub
retriever for offline tests.

  pip install fastapi uvicorn
  python scripts/serve_story_demo.py

Open http://127.0.0.1:8765 (built React from frontend/dist) or use Vite dev on :5173 with proxy to this port.
GET /api/health — RAG data readiness and version hints.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.planning.narrative_report import attach_ui_payload

FRONTEND_DIST = ROOT / "frontend" / "dist"


class PlanRequest(BaseModel):
    facts: Dict[str, Any]
    use_mock: bool = False


def _make_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles

    from src.planning.agent import PlanningAgent
    from src.planning.constraint_adapter import SimpleConstraintEngine
    from src.planning.contracts import RetrievalChunk, RetrievalChunkMetadata, RetrievalResponse
    from src.rag.client import HybridRetrievalClient
    from src.rag.readiness import hybrid_retrieval_readiness

    class MockRetrievalClient:
        def retrieve(self, query, source_hint=None, top_k=5, options=None):
            citation = "IRS Pub. 501, Filing Status"
            text = (
                "You may be able to file as head of household if you are considered "
                "unmarried, paid more than half the cost of keeping up a home, and "
                "had a qualifying person living with you for more than half the year."
            )
            q = (query or "").lower()
            if "charitable" in q or "records" in q or "contribution" in q:
                citation = "IRS Pub. 526, Contributions"
                text = (
                    "Keep written records for cash contributions and written "
                    "acknowledgments for certain larger gifts."
                )
            if source_hint == "irc":
                citation = "26 USC § 2 (illustrative)"
                text = (
                    "For purposes of this subtitle, marital status shall be determined "
                    "as of the close of the taxable year."
                )
            if source_hint == "tax_court":
                citation = "Durden v. Commissioner (2012), Dkt. 17441-09"
                text = (
                    "The court addressed substantiation of charitable contributions "
                    "under section 170 and contemporaneous written acknowledgments."
                )

            return RetrievalResponse(
                chunks=[
                    RetrievalChunk(
                        text=text,
                        metadata=RetrievalChunkMetadata(
                            source_type=source_hint or "irs_pubs",
                            citation=citation,
                            publication_year=(options or {}).get("tax_year"),
                            publication=(options or {}).get("irs_publication"),
                            page_index=1,
                        ),
                        score=0.99,
                    )
                ],
                strategy="tree" if source_hint != "tax_court" else "bm25",
                sources_queried=[source_hint] if source_hint else ["irs_pubs"],
            ).to_dict()

    app = FastAPI(
        title="Boston Tea Party 2.0",
        version="1.0",
        description="Constraint engine + planning agent + hybrid RAG. POST /api/plan",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8765",
            "http://localhost:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _hybrid: HybridRetrievalClient | None = None

    def get_retrieval(use_mock: bool):
        nonlocal _hybrid
        if use_mock:
            return MockRetrievalClient()
        if _hybrid is None:
            _hybrid = HybridRetrievalClient(repo_root=ROOT)
        return _hybrid

    @app.get("/api/health")
    def api_health() -> Dict[str, Any]:
        return {
            "ok": True,
            "constraint_engine": "SimpleConstraintEngine",
            "planning_agent": "PlanningAgent",
            "retrieval": {
                "default": "hybrid",
                "hybrid_class": "src.rag.client.HybridRetrievalClient",
                "stub": "POST /api/plan with {\"use_mock\": true}",
            },
            "rag_readiness": hybrid_retrieval_readiness(ROOT),
        }

    @app.post("/api/plan")
    def api_plan(payload: PlanRequest) -> Dict[str, Any]:
        try:
            engine = SimpleConstraintEngine()
            client = get_retrieval(payload.use_mock)
            agent = PlanningAgent(constraint_engine=engine, retrieval_client=client)
            action = agent.plan(payload.facts)
            return attach_ui_payload(action.to_dict())
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Do not mount StaticFiles at "/" — that catches /api/* and returns 404 for missing files.
    if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").exists():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="spa_assets",
            )

        @app.get("/")
        def spa_index():
            return FileResponse(FRONTEND_DIST / "index.html")

        @app.get("/{spa_path:path}")
        def spa_fallback(spa_path: str):
            if spa_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(FRONTEND_DIST / "index.html")
    else:

        @app.get("/")
        def root_build_frontend():
            return HTMLResponse(
                content=(
                    "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
                    "<title>Boston Tea Party 2.0 — build UI</title>"
                    "<style>body{font-family:system-ui,sans-serif;max-width:36rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
                    "code{background:#eee;padding:0.15rem 0.35rem}</style></head><body>"
                    "<h1>Frontend not built</h1>"
                    "<p>The API is running. Build the React app once, then reload:</p>"
                    "<pre><code>cd frontend && npm install && npm run build</code></pre>"
                    "<p>Or use Vite dev (proxies <code>/api</code> to this server):</p>"
                    "<pre><code>cd frontend && npm run dev</code></pre>"
                    "<p>Links: <a href='/docs'>OpenAPI docs</a> · <a href='/api/health'>GET /api/health</a></p>"
                    "</body></html>"
                ),
                status_code=200,
            )

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Story demo HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Install dependencies: pip install fastapi uvicorn", file=sys.stderr)
        return 1

    app = _make_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
