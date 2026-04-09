/**
 * Minimal **bold** rendering for narrative strings from the planning API.
 */
export function renderBoldSegments(text) {
  if (!text) return null;
  const parts = String(text).split(/\*\*/);
  return parts.map((p, i) =>
    i % 2 === 1 ? (
      <strong key={i}>{p}</strong>
    ) : (
      <span key={i}>{p}</span>
    )
  );
}

export function renderParagraphBlocks(text) {
  if (!text) return null;
  return String(text)
    .split(/\n\n+/)
    .filter(Boolean)
    .map((para, i) => (
      <p key={i} className="body">
        {renderBoldSegments(para)}
      </p>
    ));
}
