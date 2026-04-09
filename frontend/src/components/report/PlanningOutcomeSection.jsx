import { renderParagraphBlocks } from "../../utils/richText.jsx";
import { AdvisorySummaryPanels } from "./AdvisorySummaryPanels.jsx";
import { RetrievalDebugPanels } from "./RetrievalDebugPanels.jsx";

/**
 * Renders planner result: follow-up question or full narrative + RAG debug.
 */
export function PlanningOutcomeSection({ planResponse }) {
  if (!planResponse) return null;

  if (planResponse.error) {
    return (
      <div className="panel" id="report">
        <h2>Error</h2>
        <p>{planResponse.error}</p>
      </div>
    );
  }

  const nr = planResponse.narrative_report;
  if (!nr) return null;

  return (
    <section id="report">
            <p className="section-label">Your report</p>
      <hr className="rule-full" />

      {planResponse.action === "ask_followup" && (
        <>
          <div className="panel">
            <h2>Next question (required)</h2>
            <p className="pill">Constraint engine</p>
            <p className="question-block">{planResponse.question}</p>
            <p>
              <span className="key">Field</span> <code>{planResponse.target_field}</code>
            </p>
            {nr.followups_suggested?.length > 0 && (
              <div className="followups">
                <span className="key">Also on the checklist</span>
                <ul>
                  {nr.followups_suggested.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <AdvisorySummaryPanels narrativeReport={nr} />
        </>
      )}

      {planResponse.action === "retrieve" && (
        <>
          <AdvisorySummaryPanels narrativeReport={nr} />
                <div className="report-stack">
                  <article className="report-card">
                    <h3 className="report-card-heading">How to file</h3>
                    {renderParagraphBlocks(nr.how_to_file)}
                  </article>
                  <article className="report-card">
                    <h3 className="report-card-heading">Deductions &amp; forms</h3>
                    {renderParagraphBlocks(nr.deductions)}
                  </article>
                  <article className="report-card report-card-emphasis">
                    <h3 className="report-card-heading">Summary &amp; sources</h3>
                    {renderParagraphBlocks(nr.final_report)}
                  </article>
                </div>
          <RetrievalDebugPanels planResponse={planResponse} />
        </>
      )}
    </section>
  );
}
