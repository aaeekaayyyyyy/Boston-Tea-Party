export function BackendStatusBanner({ health, useMockRetrieval }) {
  if (!health) return null;

  const showOkStyling =
    health.ok && health.data?.rag_readiness?.ready && !useMockRetrieval;

  return (
    <div
      className={`backend-banner ${showOkStyling ? "backend-ok" : "backend-warn"}`}
      role="status"
    >
      {!health.ok && (
        <p>
          <strong>API</strong> unreachable ({health.error}). Start the server:{" "}
          <code>python scripts/serve_story_demo.py</code>
          — for dev with hot reload, run Vite on port 5173 (it proxies <code>/api</code>).
        </p>
      )}
      {health.ok && (
        <>
          <p>
            <strong>Backend</strong>: {health.data?.constraint_engine} +{" "}
            {health.data?.planning_agent}
            {useMockRetrieval ? (
              <>
                {" "}
                · retrieval mode <strong>stub</strong> (no hybrid RAG)
              </>
            ) : (
              <>
                {" "}
                · retrieval <strong>HybridRetrievalClient</strong> (IRS tree + IRC + Tax Court)
              </>
            )}
          </p>
          {!useMockRetrieval && health.data?.rag_readiness && (
            <div className="readiness-detail">
              {!health.data.rag_readiness.ready ? (
                <>
                  <p className="readiness-title">
                    RAG data gaps (hybrid retrieval may return empty passages):
                  </p>
                  <ul>
                    {(health.data.rag_readiness.issues || []).map((msg, i) => (
                      <li key={i}>{msg}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="readiness-ok">
                  On-disk RAG dependencies look present (PageIndex cache, IRC HTML, Tax Court corpus).
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
