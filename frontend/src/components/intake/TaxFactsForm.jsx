import { US_STATE_OPTIONS } from "../../lib/usStates.js";

export function TaxFactsForm({
  setFormRef,
  loading,
  statusMessage,
  useMockRetrieval,
  onUseMockRetrievalChange,
  onPresetNeedsFollowUp,
  onPresetReadyToRetrieve,
  onPresetStudentMa8843,
  onRunPlan,
}) {
  return (
    <form
      id="facts"
      ref={setFormRef}
      className="intake-form"
      onSubmit={(e) => e.preventDefault()}
    >
      <header className="intake-form-header">
        <h2 className="intake-form-title">Your situation</h2>
        <p className="intake-form-lead">
          Only <strong>Basics</strong> is required to start. Open other sections when they apply—skip what
          doesn&apos;t.
        </p>
      </header>

      <div className="intake-sections">
        <details className="intake-section" open>
          <summary className="intake-section-summary">
            <span className="intake-section-title">Basics</span>
            <span className="intake-section-hint">Tax year &amp; filing status</span>
          </summary>
          <div className="intake-section-body">
            <div className="form-grid form-grid-relaxed">
              <label className="field">
                <span className="key">Tax year</span>
                <input type="number" id="tax_year" min="2000" max="2100" />
              </label>
              <label className="field">
                <span className="key">Marital status (Dec. 31)</span>
                <select id="marital_status_on_1231" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="single">Single</option>
                  <option value="married">Married</option>
                  <option value="divorced">Divorced</option>
                  <option value="legally_separated">Legally separated</option>
                  <option value="widowed">Widowed</option>
                </select>
              </label>
              <div id="wrap_spouse_joint" className="hidden field field-span">
                <span className="key">Filing jointly with spouse?</span>
                <div className="checkbox-row">
                  <input type="checkbox" id="spouse_willing_to_file_jointly" />
                  <label htmlFor="spouse_willing_to_file_jointly">Yes, we plan to file jointly</label>
                </div>
              </div>
              <label className="field hidden" id="wrap_lived_apart">
                <span className="key">Spouse lived in your home (last 6 months)?</span>
                <select id="lived_with_spouse_last_6_months" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <div id="wrap_hoh" className="hidden intake-nested">
                <p className="intake-nested-label">Head of household — quick checks</p>
                <div className="form-grid form-grid-relaxed">
                  <label className="field">
                    <span className="key">Qualifying child?</span>
                    <select id="has_qualifying_child" defaultValue="">
                      <option value="">Choose…</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  </label>
                  <label className="field">
                    <span className="key">You paid &gt; half the cost of keeping up the home?</span>
                    <select id="paid_more_than_half_home_costs" defaultValue="">
                      <option value="">Choose…</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  </label>
                  <label className="field">
                    <span className="key">Other qualifying person in the home?</span>
                    <select id="has_other_qualifying_persons" defaultValue="">
                      <option value="">Choose…</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </details>

        <details className="intake-section">
          <summary className="intake-section-summary">
            <span className="intake-section-title">Student, residency &amp; state</span>
            <span className="intake-section-hint">Optional — use if you&apos;re an international student or unsure</span>
          </summary>
          <div className="intake-section-body">
            <p className="intake-section-intro">
              Federal <strong>tax residency</strong> isn&apos;t the same as visa status. This helps with{" "}
              <strong>Pub. 519</strong> and <strong>Form 8843</strong> when relevant.
            </p>
            <div className="form-grid form-grid-relaxed">
              <label className="field">
                <span className="key">How does the IRS see you for tax purposes?</span>
                <select id="federal_tax_residency" defaultValue="">
                  <option value="">Not sure / skip</option>
                  <option value="us_citizen_or_national">U.S. citizen or national</option>
                  <option value="us_resident_alien">Resident alien (e.g. green card or resident tests)</option>
                  <option value="nonresident_alien">Nonresident alien</option>
                  <option value="unsure">Unsure — I need Pub. 519</option>
                </select>
              </label>
              <label className="field">
                <span className="key">State you lived in most of the year</span>
                <select id="primary_state_of_residence" defaultValue="">
                  <option value="">Choose state…</option>
                  {US_STATE_OPTIONS.map(({ code, name }) => (
                    <option key={code} value={code}>
                      {name} ({code})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="key">Student in the U.S. this year?</span>
                <select id="is_student_in_us" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field hidden" id="wrap_student_visa">
                <span className="key">F-1, J-1, M-1 or similar student / exchange?</span>
                <select id="us_student_visa_f1_j1_m" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">No income or below filing threshold?</span>
                <select id="income_below_us_filing_threshold" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes — likely no Form 1040 for income</option>
                  <option value="false">No — I had income above the threshold</option>
                </select>
              </label>
            </div>
          </div>
        </details>

        <details className="intake-section">
          <summary className="intake-section-summary">
            <span className="intake-section-title">Home &amp; deductions</span>
            <span className="intake-section-hint">Mortgage, charity, itemizing</span>
          </summary>
          <div className="intake-section-body">
            <div className="form-grid form-grid-relaxed">
              <label className="field">
                <span className="key">Mortgage interest (paid)?</span>
                <select id="mortgage_interest_paid" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Charitable — cash ($)</span>
                <input type="number" id="charitable_cash_contributions" min="0" placeholder="0" />
              </label>
              <label className="field">
                <span className="key">Charitable — non-cash ($)</span>
                <input type="number" id="charitable_noncash_contributions" min="0" placeholder="0" />
              </label>
              <label className="field">
                <span className="key">Charity records in order?</span>
                <select id="charitable_contributions_documented" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Rough itemized total ($)</span>
                <input type="number" id="itemized_deductions_total" min="0" placeholder="If known" />
              </label>
              <label className="field">
                <span className="key">Itemizing vs standard?</span>
                <select id="itemized_deductions_exceed_standard" defaultValue="">
                  <option value="">Not sure</option>
                  <option value="true">Itemizing is higher</option>
                  <option value="false">Standard is higher</option>
                </select>
              </label>
            </div>
          </div>
        </details>

        <details className="intake-section">
          <summary className="intake-section-summary">
            <span className="intake-section-title">Income &amp; credits</span>
            <span className="intake-section-hint">W-2, investments, dependents, age</span>
          </summary>
          <div className="intake-section-body">
            <p className="intake-section-intro">
              Helps suggest which schedules and forms to review. All optional.
            </p>
            <div className="form-grid form-grid-relaxed">
              <label className="field">
                <span className="key">W-2 wages?</span>
                <select id="has_w2_income" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Self-employment / gig?</span>
                <select id="has_self_employment_income" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Interest or dividends?</span>
                <select id="has_interest_or_dividend_income" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Sold investments or property?</span>
                <select id="has_capital_asset_sales" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Children under 17 (CTC)?</span>
                <select id="has_qualifying_children_under_17" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Age 65+ at year-end?</span>
                <select id="taxpayer_age_65_or_older" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Legally blind (IRS definition)?</span>
                <select id="taxpayer_blind" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">State / local taxes paid?</span>
                <select id="paid_state_local_taxes" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label className="field">
                <span className="key">Large medical expenses?</span>
                <select id="had_significant_medical_expenses" defaultValue="">
                  <option value="">Choose…</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
            </div>
          </div>
        </details>
      </div>

      <div className="intake-footer">
        <div className="intake-presets">
          <span className="intake-presets-label">Examples</span>
          <button type="button" className="preset-chip" onClick={onPresetNeedsFollowUp}>
            Married — needs one more answer
          </button>
          <button type="button" className="preset-chip" onClick={onPresetReadyToRetrieve}>
            Married — ready for report
          </button>
          <button type="button" className="preset-chip" onClick={onPresetStudentMa8843}>
            Student in MA (8843)
          </button>
        </div>
        <div className="intake-run-row">
          <label className="intake-stub-toggle">
            <input
              type="checkbox"
              checked={useMockRetrieval}
              onChange={(e) => onUseMockRetrievalChange(e.target.checked)}
            />
            <span>Stub retrieval (offline)</span>
          </label>
          <button type="button" className="primary intake-run-btn" disabled={loading} onClick={onRunPlan}>
            {loading ? "Running…" : "Run plan"}
          </button>
        </div>
        {statusMessage ? <p className="intake-status">{statusMessage}</p> : null}
      </div>
    </form>
  );
}
