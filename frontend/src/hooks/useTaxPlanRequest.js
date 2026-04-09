import { useCallback, useState } from "react";
import { collectFactsFromForm } from "../lib/taxFactsDom.js";

/**
 * POST /api/plan with facts from the form; tracks loading and API errors.
 */
export function useTaxPlanRequest(formEl) {
  const [useMockRetrieval, setUseMockRetrieval] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [planResponse, setPlanResponse] = useState(null);

  const runPlan = useCallback(async () => {
    if (!formEl) return;
    setLoading(true);
    setStatusMessage("Consulting the planning clerk…");
    setPlanResponse(null);
    const facts = collectFactsFromForm(formEl);
    try {
      const r = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facts, use_mock: useMockRetrieval }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || data.error || r.statusText);
      setPlanResponse(data);
      setStatusMessage("");
    } catch (e) {
      setPlanResponse({ error: String(e.message || e) });
      setStatusMessage("");
    } finally {
      setLoading(false);
    }
  }, [formEl, useMockRetrieval]);

  return {
    runPlan,
    loading,
    statusMessage,
    planResponse,
    useMockRetrieval,
    setUseMockRetrieval,
  };
}
