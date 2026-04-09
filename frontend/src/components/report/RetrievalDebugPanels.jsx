export function RetrievalDebugPanels({ planResponse }) {
  const preview = planResponse?.retrieval_preview || [];
  const calls = planResponse?.retrieval_calls || [];

  return (
    <>
      <details className="tech">
        <summary>Compact authority excerpts (optional detail)</summary>
        {preview.map((res, i) => (
          <div key={i} style={{ marginTop: "1rem" }}>
            <span className="pill">{calls[i]?.source_hint || "—"}</span>
            {(res.chunks || []).map((ch, j) => (
              <div key={j} className="chunk-mini">
                <div className="cite">{ch.metadata?.citation || "—"}</div>
                <div>{ch.text}</div>
              </div>
            ))}
          </div>
        ))}
      </details>

      <details className="tech" style={{ marginTop: "0.75rem" }}>
        <summary>Full technical JSON (RAG)</summary>
        <pre
          style={{
            fontSize: "0.7rem",
            overflow: "auto",
            maxHeight: "18rem",
            marginTop: "0.5rem",
          }}
        >
          {JSON.stringify(planResponse.retrieval_results ?? [], null, 2)}
        </pre>
      </details>
    </>
  );
}
