import FieldsSection from "./FieldsSection.jsx";
import SingleResultSection from "./SingleResultSection.jsx";

function SingleFlow({
  checkedSeconds,
  coldStartHint,
  errorMessage,
  formValues,
  handleImageChange,
  handleSubmit,
  imagePreviewUrl,
  isBusy,
  isProcessingImage,
  isSubmitting,
  result,
  selectedFileName,
  singleErrorRef,
  singleFileInputRef,
  startOver,
  updateField,
  verdictLabel,
}) {
  return (
    <>
      <form className="verification-layout" aria-busy={isBusy} onSubmit={handleSubmit}>
        <section className="photo-section" aria-labelledby="photo-heading">
          <div>
            <h2 id="photo-heading">Label Photo</h2>
            <p className="section-note">Image file up to 20 MB.</p>
          </div>

          <button
            aria-controls="single-label-photo"
            className="file-button"
            disabled={isBusy}
            type="button"
            onClick={() => singleFileInputRef.current?.click()}
          >
            Choose Label Photo
          </button>
          <input
            id="single-label-photo"
            ref={singleFileInputRef}
            className="file-input"
            type="file"
            aria-label="Choose one label photo"
            accept="image/*"
            disabled={isBusy}
            onChange={handleImageChange}
          />

          {imagePreviewUrl ? (
            <div className="image-preview-row">
              <img alt="Selected label preview" className="image-preview" src={imagePreviewUrl} />
              <div>
                <strong>{selectedFileName}</strong>
                <p>{isProcessingImage ? "Preparing photo..." : "Photo ready"}</p>
              </div>
            </div>
          ) : (
            <div className="empty-photo">No photo selected</div>
          )}
        </section>

        <FieldsSection formValues={formValues} isBusy={isBusy} updateField={updateField} />

        {errorMessage ? (
          <div className="alert" ref={singleErrorRef} role="alert" tabIndex={-1}>
            {errorMessage}
          </div>
        ) : null}

        {isBusy ? (
          <div className="status-band" role="status">
            <span>{isProcessingImage ? "Preparing the photo now." : "Checking the photo now."}</span>
            {coldStartHint ? <span className="cold-start-hint">{coldStartHint}</span> : null}
          </div>
        ) : null}

        <div className="action-row">
          <button className="submit-button" disabled={isBusy} type="submit">
            {isSubmitting ? "Checking Label..." : "Verify Label"}
          </button>
          {result ? (
            <button className="secondary-button" disabled={isBusy} type="button" onClick={startOver}>
              Start Over
            </button>
          ) : null}
        </div>
      </form>

      {result ? (
        <SingleResultSection
          checkedSeconds={checkedSeconds}
          result={result}
          verdictLabel={verdictLabel}
        />
      ) : null}
    </>
  );
}

export default SingleFlow;
