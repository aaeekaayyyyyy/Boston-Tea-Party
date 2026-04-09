/**
 * DOM helpers for the tax facts form (field ids must match backend intake keys).
 */

export const ADVISORY_TRI_STATE_FIELD_IDS = [
  "has_w2_income",
  "has_self_employment_income",
  "has_interest_or_dividend_income",
  "has_capital_asset_sales",
  "has_qualifying_children_under_17",
  "taxpayer_age_65_or_older",
  "taxpayer_blind",
  "paid_state_local_taxes",
  "had_significant_medical_expenses",
  "itemized_deductions_exceed_standard",
];

function readNumberField(form, id) {
  const el = form.querySelector(`#${id}`);
  if (!el || el.value === "") return undefined;
  const n = Number(el.value);
  return Number.isFinite(n) ? n : undefined;
}

function readTriStateSelect(form, id) {
  const el = form.querySelector(`#${id}`);
  if (!el || el.value === "") return undefined;
  return el.value === "true";
}

/**
 * @param {HTMLFormElement} form
 * @returns {Record<string, unknown>}
 */
export function collectFactsFromForm(form) {
  const facts = {};

  const ty = readNumberField(form, "tax_year");
  if (ty !== undefined) facts.tax_year = ty;

  const ms = form.querySelector("#marital_status_on_1231")?.value?.trim();
  if (ms) facts.marital_status_on_1231 = ms;

  const fedRes = form.querySelector("#federal_tax_residency")?.value?.trim();
  if (fedRes) facts.federal_tax_residency = fedRes;
  const stateLive = form.querySelector("#primary_state_of_residence")?.value?.trim();
  if (stateLive) facts.primary_state_of_residence = stateLive;

  const stuUs = readTriStateSelect(form, "is_student_in_us");
  if (stuUs !== undefined) facts.is_student_in_us = stuUs;
  const stuVisa = readTriStateSelect(form, "us_student_visa_f1_j1_m");
  if (stuVisa !== undefined) facts.us_student_visa_f1_j1_m = stuVisa;
  const belowThr = readTriStateSelect(form, "income_below_us_filing_threshold");
  if (belowThr !== undefined) facts.income_below_us_filing_threshold = belowThr;

  const wrapSj = form.querySelector("#wrap_spouse_joint");
  if (wrapSj && !wrapSj.classList.contains("hidden")) {
    facts.spouse_willing_to_file_jointly = form.querySelector(
      "#spouse_willing_to_file_jointly"
    ).checked;
  }

  const lived = readTriStateSelect(form, "lived_with_spouse_last_6_months");
  if (lived !== undefined) facts.lived_with_spouse_last_6_months = lived;

  const qc = readTriStateSelect(form, "has_qualifying_child");
  if (qc !== undefined) facts.has_qualifying_child = qc;
  const op = readTriStateSelect(form, "has_other_qualifying_persons");
  if (op !== undefined) facts.has_other_qualifying_persons = op;
  const ph = readTriStateSelect(form, "paid_more_than_half_home_costs");
  if (ph !== undefined) facts.paid_more_than_half_home_costs = ph;

  const cash = readNumberField(form, "charitable_cash_contributions");
  const nc = readNumberField(form, "charitable_noncash_contributions");
  if (cash !== undefined) facts.charitable_cash_contributions = cash;
  if (nc !== undefined) facts.charitable_noncash_contributions = nc;

  const cd = readTriStateSelect(form, "charitable_contributions_documented");
  if (cd !== undefined) facts.charitable_contributions_documented = cd;

  const it = readNumberField(form, "itemized_deductions_total");
  if (it !== undefined) facts.itemized_deductions_total = it;

  const mig = readTriStateSelect(form, "mortgage_interest_paid");
  if (mig !== undefined) facts.mortgage_interest_paid = mig;

  for (const k of ADVISORY_TRI_STATE_FIELD_IDS) {
    const v = readTriStateSelect(form, k);
    if (v !== undefined) facts[k] = v;
  }

  return facts;
}

/**
 * Show / hide conditional sections (married, HoH, student visa).
 * @param {HTMLFormElement} form
 */
export function syncConditionalFieldVisibility(form) {
  const ms = form.querySelector("#marital_status_on_1231")?.value;
  const married = ms === "married";
  const joint = form.querySelector("#spouse_willing_to_file_jointly")?.checked;
  const livedVal = form.querySelector("#lived_with_spouse_last_6_months")?.value;

  const wrapSj = form.querySelector("#wrap_spouse_joint");
  const wrapLived = form.querySelector("#wrap_lived_apart");
  const wrapHoh = form.querySelector("#wrap_hoh");

  if (wrapSj) wrapSj.classList.toggle("hidden", !married);
  if (wrapLived) wrapLived.classList.toggle("hidden", !married || joint);
  if (wrapHoh)
    wrapHoh.classList.toggle("hidden", !(married && !joint && livedVal === "false"));

  const studentUs = form.querySelector("#is_student_in_us")?.value;
  const wrapStudentVisa = form.querySelector("#wrap_student_visa");
  if (wrapStudentVisa) wrapStudentVisa.classList.toggle("hidden", studentUs !== "true");
}
