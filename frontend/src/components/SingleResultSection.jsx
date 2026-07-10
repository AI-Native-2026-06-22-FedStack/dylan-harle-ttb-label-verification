import ResultRow from "./ResultRow.jsx";

function SingleResultSection({ checkedSeconds, result, verdictLabel }) {
  return (
    <section className="results-section" aria-labelledby="results-heading" aria-live="polite">
      <div className={`verdict-band ${result.overall_verdict === "APPROVED" ? "approved" : "review"}`}>
        <p>Result</p>
        <h2 id="results-heading">{verdictLabel}</h2>
        {checkedSeconds ? <span>Checked in {checkedSeconds} seconds</span> : null}
      </div>

      <div className="results-list">
        {result.results.map((field) => (
          <ResultRow field={field} key={field.field} />
        ))}
      </div>
    </section>
  );
}

export default SingleResultSection;
