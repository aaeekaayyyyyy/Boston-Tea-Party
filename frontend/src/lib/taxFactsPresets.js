import { ADVISORY_TRI_STATE_FIELD_IDS, syncConditionalFieldVisibility } from "./taxFactsDom.js";

function clearAdvisoryTriStates(form) {
  for (const id of ADVISORY_TRI_STATE_FIELD_IDS) {
    const el = form.querySelector(`#${id}`);
    if (el) el.value = "";
  }
}

function setAdvisoryAllFalse(form) {
  for (const id of ADVISORY_TRI_STATE_FIELD_IDS) {
    const el = form.querySelector(`#${id}`);
    if (el) el.value = "false";
  }
}

/**
 * @param {HTMLFormElement} form
 */
export function seedDefaultFormValues(form) {
  form.querySelector("#tax_year").value = "2025";
  form.querySelector("#marital_status_on_1231").value = "married";
  form.querySelector("#spouse_willing_to_file_jointly").checked = false;
  form.querySelector("#charitable_cash_contributions").value = "750";
  syncConditionalFieldVisibility(form);
}

/**
 * @param {HTMLFormElement} form
 */
export function applyPresetNeedsFollowUp(form) {
  form.querySelector("#tax_year").value = "2025";
  form.querySelector("#marital_status_on_1231").value = "married";
  form.querySelector("#spouse_willing_to_file_jointly").checked = false;
  form.querySelector("#lived_with_spouse_last_6_months").value = "";
  form.querySelector("#has_qualifying_child").value = "";
  form.querySelector("#paid_more_than_half_home_costs").value = "";
  form.querySelector("#has_other_qualifying_persons").value = "";
  form.querySelector("#charitable_cash_contributions").value = "750";
  form.querySelector("#charitable_noncash_contributions").value = "";
  form.querySelector("#charitable_contributions_documented").value = "";
  form.querySelector("#itemized_deductions_total").value = "";
  form.querySelector("#mortgage_interest_paid").value = "";
  clearAdvisoryTriStates(form);
  form.querySelector("#federal_tax_residency").value = "";
  form.querySelector("#primary_state_of_residence").value = "";
  form.querySelector("#is_student_in_us").value = "";
  form.querySelector("#us_student_visa_f1_j1_m").value = "";
  form.querySelector("#income_below_us_filing_threshold").value = "";
  syncConditionalFieldVisibility(form);
}

/**
 * @param {HTMLFormElement} form
 */
export function applyPresetReadyToRetrieve(form) {
  applyPresetNeedsFollowUp(form);
  form.querySelector("#lived_with_spouse_last_6_months").value = "false";
  form.querySelector("#has_qualifying_child").value = "true";
  form.querySelector("#paid_more_than_half_home_costs").value = "true";
  form.querySelector("#charitable_contributions_documented").value = "true";
  form.querySelector("#itemized_deductions_total").value = "9000";
  form.querySelector("#mortgage_interest_paid").value = "true";
  form.querySelector("#has_w2_income").value = "true";
  form.querySelector("#has_self_employment_income").value = "false";
  form.querySelector("#has_qualifying_children_under_17").value = "true";
  form.querySelector("#itemized_deductions_exceed_standard").value = "true";
  form.querySelector("#paid_state_local_taxes").value = "true";
  syncConditionalFieldVisibility(form);
}

/**
 * Nonresident student in MA, no income — exercises 8843 / Pub. 519 advisory path.
 * @param {HTMLFormElement} form
 */
export function applyPresetStudentMa8843(form) {
  form.querySelector("#tax_year").value = "2025";
  form.querySelector("#marital_status_on_1231").value = "single";
  form.querySelector("#federal_tax_residency").value = "nonresident_alien";
  form.querySelector("#primary_state_of_residence").value = "MA";
  form.querySelector("#is_student_in_us").value = "true";
  form.querySelector("#us_student_visa_f1_j1_m").value = "true";
  form.querySelector("#income_below_us_filing_threshold").value = "true";
  form.querySelector("#charitable_cash_contributions").value = "0";
  form.querySelector("#charitable_noncash_contributions").value = "0";
  form.querySelector("#itemized_deductions_total").value = "0";
  form.querySelector("#mortgage_interest_paid").value = "false";
  form.querySelector("#charitable_contributions_documented").value = "false";
  setAdvisoryAllFalse(form);
  syncConditionalFieldVisibility(form);
}
