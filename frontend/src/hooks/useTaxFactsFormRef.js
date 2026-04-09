import { useCallback, useEffect, useState } from "react";
import { syncConditionalFieldVisibility } from "../lib/taxFactsDom.js";

/**
 * Holds the tax facts form element and keeps conditional sections in sync on change.
 */
export function useTaxFactsFormRef() {
  const [formEl, setFormEl] = useState(null);

  const setFormRef = useCallback((node) => {
    if (node) {
      setFormEl(node);
      syncConditionalFieldVisibility(node);
    }
  }, []);

  useEffect(() => {
    if (!formEl) return;
    const onChange = () => syncConditionalFieldVisibility(formEl);
    formEl.addEventListener("change", onChange);
    return () => formEl.removeEventListener("change", onChange);
  }, [formEl]);

  return { formEl, setFormRef };
}
