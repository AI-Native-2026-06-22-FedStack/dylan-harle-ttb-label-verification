import { displayValue, failureReason, labelForField } from "../lib/display.js";

function ResultRow({ field }) {
  const isPass = field.status === "PASS";
  const label = labelForField(field.field);

  return (
    <article className={`result-row ${isPass ? "pass" : "fail"}`}>
      <div className="result-row-heading">
        <h3>{label}</h3>
        <span className={`status-pill ${isPass ? "pass" : "fail"}`}>{field.status}</span>
      </div>
      <p className="field-reason">{isPass ? "Matches" : failureReason(field)}</p>

      {!isPass ? (
        <>
          <div className="comparison-grid">
            <div>
              <span>Application Says</span>
              <p>{displayValue(field.expected)}</p>
            </div>
            <div>
              <span>Found on Label</span>
              <p>{displayValue(field.found)}</p>
            </div>
          </div>
          {field.field === "government_warning" ? (
            <div className="alert">
              <strong>Extracted warning</strong>
              <p>{displayValue(field.found)}</p>
            </div>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

export default ResultRow;
