import FieldsSection from "./FieldsSection.jsx";
import BatchResultsSection from "./BatchResultsSection.jsx";
import { INITIAL_FORM } from "../lib/formConfig.js";

function BatchFlow({
  batchErrorMessage,
  batchErrorRef,
  batchFileInputRef,
  batchItems,
  batchPrepareProgress,
  batchResult,
  batchSeconds,
  coldStartHint,
  handleBatchFilesChange,
  handleBatchSubmit,
  isBatchBusy,
  isPreparingBatch,
  isSubmittingBatch,
  selectedBatchFormItem,
  selectedBatchIndex,
  selectedBatchResultItem,
  setSelectedBatchIndex,
  showBatchServerProgress,
  startBatchOver,
  updateBatchItemField,
}) {
  return (
    <>
      <form className="verification-layout" aria-busy={isBatchBusy} onSubmit={handleBatchSubmit}>
        <section className="photo-section" aria-labelledby="batch-photo-heading">
          <div>
            <h2 id="batch-photo-heading">Label Photos</h2>
            <p className="section-note">Image files up to 20 MB each. Up to 10 photos.</p>
          </div>

          <button
            aria-controls="batch-label-photos"
            className="file-button"
            disabled={isBatchBusy}
            type="button"
            onClick={() => batchFileInputRef.current?.click()}
          >
            Choose Label Photos
          </button>
          <input
            id="batch-label-photos"
            ref={batchFileInputRef}
            className="file-input"
            type="file"
            multiple
            aria-label="Choose label photos for batch verification"
            accept="image/*"
            disabled={isBatchBusy}
            onChange={handleBatchFilesChange}
          />

          {batchItems.length ? (
            <div className="batch-file-list">
              {batchItems.map((item, index) => (
                <button
                  className={`batch-file ${item.error ? "file-error" : ""} ${selectedBatchIndex === index ? "selected" : ""}`}
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedBatchIndex(index)}
                >
                  <img alt="" className="batch-thumb" src={item.previewUrl} />
                  <div>
                    <strong>
                      {index + 1}. {item.originalName}
                    </strong>
                    <p>{item.error || "Photo ready"}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-photo">No photos selected</div>
          )}
        </section>

        <FieldsSection
          formValues={selectedBatchFormItem?.applicationValues || INITIAL_FORM}
          isBusy={isBatchBusy || !selectedBatchFormItem}
          updateField={updateBatchItemField}
        />

        {batchErrorMessage ? (
          <div className="alert" ref={batchErrorRef} role="alert" tabIndex={-1}>
            {batchErrorMessage}
          </div>
        ) : null}

        {isPreparingBatch ? (
          <div className="status-band" role="status">
            Preparing photos {batchPrepareProgress.done} of {batchPrepareProgress.total}.
          </div>
        ) : null}

        {showBatchServerProgress ? (
          <div className="status-band progress-band" role="status">
            <span>Checking labels now.</span>
            {coldStartHint ? <span className="cold-start-hint">{coldStartHint}</span> : null}
            <span className="progress-track" aria-hidden="true">
              <span />
            </span>
          </div>
        ) : null}

        <div className="action-row">
          <button className="submit-button" disabled={isBatchBusy} type="submit">
            {isSubmittingBatch ? "Checking Batch..." : "Verify Batch"}
          </button>
          {batchResult ? (
            <button
              className="secondary-button"
              disabled={isBatchBusy}
              type="button"
              onClick={startBatchOver}
            >
              Start Over
            </button>
          ) : null}
        </div>
      </form>

      {batchResult ? (
        <BatchResultsSection
          batchResult={batchResult}
          batchSeconds={batchSeconds}
          selectedBatchIndex={selectedBatchIndex}
          selectedBatchItem={selectedBatchResultItem}
          setSelectedBatchIndex={setSelectedBatchIndex}
        />
      ) : null}
    </>
  );
}

export default BatchFlow;
