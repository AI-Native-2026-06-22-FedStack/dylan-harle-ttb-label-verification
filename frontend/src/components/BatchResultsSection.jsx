import { statusClass, statusLabel } from "../lib/display.js";
import ResultRow from "./ResultRow.jsx";

function BatchResultsSection({
  batchResult,
  batchSeconds,
  selectedBatchIndex,
  selectedBatchItem,
  setSelectedBatchIndex,
}) {
  return (
    <section className="results-section" aria-labelledby="batch-results-heading" aria-live="polite">
      <div className="batch-summary">
        <div>
          <p>Total</p>
          <strong>{batchResult.summary.total}</strong>
        </div>
        <div>
          <p>Approved</p>
          <strong>{batchResult.summary.passed}</strong>
        </div>
        <div>
          <p>Needs Review</p>
          <strong>{batchResult.summary.needs_review}</strong>
        </div>
      </div>
      {batchSeconds ? <p className="batch-time">Checked in {batchSeconds} seconds</p> : null}

      <div className="batch-results-layout">
        <div className="batch-item-list" aria-label="Batch results">
          {batchResult.items.map((item, index) => (
            <button
              className={`batch-result-button ${selectedBatchIndex === index ? "selected" : ""} ${statusClass(item.status)}`}
              key={`${item.filename}-${item.index}`}
              type="button"
              onClick={() => setSelectedBatchIndex(index)}
            >
              <span>{item.filename}</span>
              <strong>{statusLabel(item.status)}</strong>
            </button>
          ))}
        </div>

        <div className="batch-detail">
          {selectedBatchItem ? (
            <>
              <div className={`detail-heading ${statusClass(selectedBatchItem.status)}`}>
                <p>Selected Label</p>
                <h2>{selectedBatchItem.filename}</h2>
                <strong>{statusLabel(selectedBatchItem.status)}</strong>
              </div>

              {selectedBatchItem.error ? (
                <div className="alert" role="alert">
                  {selectedBatchItem.error.message}
                </div>
              ) : null}

              {selectedBatchItem.result ? (
                <div className="results-list">
                  {selectedBatchItem.result.results.map((field) => (
                    <ResultRow field={field} key={field.field} />
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default BatchResultsSection;
