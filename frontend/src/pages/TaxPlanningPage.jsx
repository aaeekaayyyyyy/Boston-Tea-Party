import { useEffect } from "react";
import { BackendStatusBanner } from "../components/BackendStatusBanner.jsx";
import { TaxFactsForm } from "../components/intake/TaxFactsForm.jsx";
import { AppShellFooter } from "../components/layout/AppShellFooter.jsx";
import { AppShellHeader } from "../components/layout/AppShellHeader.jsx";
import { PlanningOutcomeSection } from "../components/report/PlanningOutcomeSection.jsx";
import { useBackendHealth } from "../hooks/useBackendHealth.js";
import { useTaxFactsFormRef } from "../hooks/useTaxFactsFormRef.js";
import { useTaxPlanRequest } from "../hooks/useTaxPlanRequest.js";
import {
  applyPresetNeedsFollowUp,
  applyPresetReadyToRetrieve,
  applyPresetStudentMa8843,
  seedDefaultFormValues,
} from "../lib/taxFactsPresets.js";
import "../styles/tax-planning.css";

/**
 * Root UI: tax facts intake → POST /api/plan → narrative + RAG preview.
 */
export default function TaxPlanningPage() {
  const backendHealth = useBackendHealth();
  const { formEl, setFormRef } = useTaxFactsFormRef();
  const {
    runPlan,
    loading,
    statusMessage,
    planResponse,
    useMockRetrieval,
    setUseMockRetrieval,
  } = useTaxPlanRequest(formEl);

  useEffect(() => {
    if (!formEl) return;
    seedDefaultFormValues(formEl);
  }, [formEl]);

  return (
    <div className="app">
      <AppShellHeader />

      <main className="main">
        <BackendStatusBanner health={backendHealth} useMockRetrieval={useMockRetrieval} />

        <p className="section-label">Your tax picture</p>
        <hr className="rule-full" />

        <TaxFactsForm
          setFormRef={setFormRef}
          loading={loading}
          statusMessage={statusMessage}
          useMockRetrieval={useMockRetrieval}
          onUseMockRetrievalChange={setUseMockRetrieval}
          onPresetNeedsFollowUp={() => formEl && applyPresetNeedsFollowUp(formEl)}
          onPresetReadyToRetrieve={() => formEl && applyPresetReadyToRetrieve(formEl)}
          onPresetStudentMa8843={() => formEl && applyPresetStudentMa8843(formEl)}
          onRunPlan={runPlan}
        />

        {planResponse && <PlanningOutcomeSection planResponse={planResponse} />}
      </main>

      <AppShellFooter />
    </div>
  );
}
