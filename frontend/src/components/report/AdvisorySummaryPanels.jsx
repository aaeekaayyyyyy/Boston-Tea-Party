import { renderBoldSegments, renderParagraphBlocks } from "../../utils/richText.jsx";

/**
 * Narrative report slices: taxpayer position, IRS forms, optional advisory follow-ups.
 */
export function AdvisorySummaryPanels({ narrativeReport: nr }) {
  const pos = nr?.taxpayer_position;
  const forms = nr?.forms_and_schedules || [];
  const adv = nr?.advisory_followups || [];
  if (!pos) return null;

  return (
    <>
      <div className="panel position-panel">
        <h2>Position &amp; rule paths</h2>
        <p className="headline-lead">{renderBoldSegments(pos.headline)}</p>
        {renderParagraphBlocks(pos.detail)}
        {pos.path_explanations?.length > 0 && (
          <ul className="path-list">
            {pos.path_explanations.map((p) => (
              <li key={p.path_id}>
                <strong>{p.label}</strong> — {p.note}
              </li>
            ))}
          </ul>
        )}
        {pos.confidence && (
          <p className="confidence-pill">
            <span className="key">Confidence</span> {pos.confidence}
          </p>
        )}
        <p className="meta-tiny">{pos.rules_index_note}</p>
      </div>

      <div className="panel forms-panel">
        <h2>Forms &amp; schedules (how to approach them)</h2>
        <p className="status subtle">
          Educational only—not personalized tax advice. Follow each form&apos;s IRS instructions for the
          tax year.
        </p>
        <div className="forms-stack">
          {forms.length === 0 ? (
            <p className="empty-hint subtle">
              Add income and deduction facts above to populate likely schedules (1040 is always the core
              return).
            </p>
          ) : (
            forms.map((f, i) => (
              <details key={i} className="form-card" open={i < 3}>
                <summary>
                  <strong>{f.form}</strong> — {f.title}
                </summary>
                <p className="when">{f.when_applies}</p>
                <ol className="how-steps">
                  {(f.how_to_fill || []).map((step, j) => (
                    <li key={j}>{renderBoldSegments(String(step))}</li>
                  ))}
                </ol>
                {f.irs && (
                  <a className="irs-link" href={f.irs} target="_blank" rel="noreferrer">
                    IRS form / publication →
                  </a>
                )}
              </details>
            ))
          )}
        </div>
      </div>

      {adv.length > 0 && (
        <div className="panel advisory-panel">
          <h2>Suggested questions (sharper return)</h2>
          <p className="status subtle">
            These are not required for the engine to run, but they mirror situations in{" "}
            <code>src/rules/</code> and improve your report.
          </p>
          <ul className="advisory-list">
            {adv.map((a, i) => (
              <li key={i}>
                <span className="advisory-q">{renderBoldSegments(a.question)}</span>
                <span className="why"> — {renderBoldSegments(a.why_matters)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
