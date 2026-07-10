import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

const MAX_ORIGINAL_BYTES = 20 * 1024 * 1024;
const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const MAX_BATCH_IMAGES = 10;
const MAX_IMAGE_EDGE = 1280;
const JPEG_QUALITY = 0.85;
const MIN_JPEG_QUALITY = 0.82;
const SUPPORTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

const STANDARD_WARNING =
  "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS.";

const FIELD_CONFIGS = [
  { key: "brand_name", label: "Brand Name", type: "input", maxLength: 160 },
  { key: "class_type", label: "Product Type", type: "input", maxLength: 160 },
  { key: "producer", label: "Producer Name", type: "input", maxLength: 200 },
  { key: "country_of_origin", label: "Country of Origin", type: "input", maxLength: 120 },
  { key: "abv", label: "Alcohol by Volume", type: "input", maxLength: 80 },
  { key: "net_contents", label: "Net Contents", type: "input", maxLength: 80 },
  { key: "government_warning", label: "Government Warning", type: "textarea", maxLength: 650 },
];

const INITIAL_FORM = {
  brand_name: "",
  class_type: "",
  producer: "",
  country_of_origin: "",
  abv: "",
  net_contents: "",
  government_warning: STANDARD_WARNING,
};

function App() {
  const singleFileInputRef = useRef(null);
  const batchFileInputRef = useRef(null);
  const batchProgressTimerRef = useRef(null);
  const singleErrorRef = useRef(null);
  const batchErrorRef = useRef(null);
  const [mode, setMode] = useState("single");
  const [formValues, setFormValues] = useState(INITIAL_FORM);

  const [selectedFileName, setSelectedFileName] = useState("");
  const [imagePreviewUrl, setImagePreviewUrl] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [isProcessingImage, setIsProcessingImage] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState(null);

  const [batchItems, setBatchItems] = useState([]);
  const [batchPrepareProgress, setBatchPrepareProgress] = useState({ done: 0, total: 0 });
  const [isPreparingBatch, setIsPreparingBatch] = useState(false);
  const [isSubmittingBatch, setIsSubmittingBatch] = useState(false);
  const [showBatchServerProgress, setShowBatchServerProgress] = useState(false);
  const [batchErrorMessage, setBatchErrorMessage] = useState("");
  const [batchResult, setBatchResult] = useState(null);
  const [selectedBatchIndex, setSelectedBatchIndex] = useState(0);

  const isBusy = isProcessingImage || isSubmitting;
  const isBatchBusy = isPreparingBatch || isSubmittingBatch;
  const verdictLabel = result?.overall_verdict === "APPROVED" ? "APPROVED" : "NEEDS REVIEW";
  const checkedSeconds = useMemo(() => formatSeconds(result?.latency_ms), [result]);
  const batchSeconds = useMemo(() => formatSeconds(batchResult?.latency_ms), [batchResult]);
  const selectedBatchFormItem = batchItems[selectedBatchIndex] || null;
  const selectedBatchResultItem = batchResult?.items?.[selectedBatchIndex] || null;

  useEffect(() => {
    return () => {
      if (imagePreviewUrl) {
        URL.revokeObjectURL(imagePreviewUrl);
      }
    };
  }, [imagePreviewUrl]);

  useEffect(() => {
    return () => {
      batchItems.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    };
  }, [batchItems]);

  useEffect(() => {
    return () => {
      if (batchProgressTimerRef.current) {
        window.clearTimeout(batchProgressTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (errorMessage) {
      singleErrorRef.current?.focus();
    }
  }, [errorMessage]);

  useEffect(() => {
    if (batchErrorMessage) {
      batchErrorRef.current?.focus();
    }
  }, [batchErrorMessage]);

  function updateField(field, value) {
    setFormValues((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function updateBatchItemField(field, value) {
    setBatchItems((current) =>
      current.map((item, index) =>
        index === selectedBatchIndex
          ? {
              ...item,
              applicationValues: {
                ...item.applicationValues,
                [field]: value,
              },
            }
          : item,
      ),
    );
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setErrorMessage("");
    setBatchErrorMessage("");
  }

  async function handleImageChange(event) {
    const file = event.target.files?.[0];
    setErrorMessage("");
    setResult(null);
    clearSelectedImage();

    if (!file) {
      return;
    }

    const validationError = validateOriginalFile(file);
    if (validationError) {
      setErrorMessage(validationError);
      event.target.value = "";
      return;
    }

    const previewUrl = URL.createObjectURL(file);
    setImagePreviewUrl(previewUrl);
    setSelectedFileName(file.name);
    setIsProcessingImage(true);

    try {
      const processedFile = await prepareImageForUpload(file);
      setUploadFile(processedFile);
    } catch (imageError) {
      URL.revokeObjectURL(previewUrl);
      setImagePreviewUrl("");
      setSelectedFileName("");
      setErrorMessage(
        imageError instanceof Error
          ? imageError.message
          : "We could not prepare that photo. Please try another label photo.",
      );
      event.target.value = "";
    } finally {
      setIsProcessingImage(false);
    }
  }

  async function handleBatchFilesChange(event) {
    const files = Array.from(event.target.files || []);
    clearBatchSelection();
    setBatchErrorMessage("");
    setBatchResult(null);
    setSelectedBatchIndex(0);

    if (files.length === 0) {
      return;
    }

    if (files.length > MAX_BATCH_IMAGES) {
      setBatchErrorMessage("Please choose 10 or fewer label photos.");
      event.target.value = "";
      return;
    }

    setIsPreparingBatch(true);
    setBatchPrepareProgress({ done: 0, total: files.length });

    const nextItems = [];

    for (const [index, file] of files.entries()) {
      const validationError = validateOriginalFile(file);
      const previewUrl = URL.createObjectURL(file);
      const item = {
        id: `${file.name}-${file.lastModified}-${index}`,
        originalName: file.name,
        previewUrl,
        uploadFile: null,
        error: validationError,
        applicationValues: { ...formValues },
      };

      if (!validationError) {
        try {
          item.uploadFile = await prepareImageForUpload(file);
        } catch (imageError) {
          item.error =
            imageError instanceof Error
              ? imageError.message
              : "We could not prepare this photo. Please try another label photo.";
        }
      }

      nextItems.push(item);
      setBatchItems([...nextItems]);
      setBatchPrepareProgress({ done: index + 1, total: files.length });
    }

    setIsPreparingBatch(false);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setResult(null);

    const formError = validateFormFields();
    if (formError) {
      setErrorMessage(formError);
      return;
    }

    if (!uploadFile) {
      setErrorMessage("Please choose a label photo.");
      return;
    }

    setIsSubmitting(true);

    try {
      const body = buildFormData();
      body.append("image", uploadFile);

      const response = await fetch(`${API_BASE_URL}/verify`, {
        method: "POST",
        body,
      });
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(readableApiError(payload));
      }

      setResult(payload);
    } catch (submitError) {
      setErrorMessage(
        submitError instanceof Error
          ? submitError.message
          : "Verification failed. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleBatchSubmit(event) {
    event.preventDefault();
    setBatchErrorMessage("");
    setBatchResult(null);
    setSelectedBatchIndex(0);

    const formError = validateBatchFormFields();
    if (formError) {
      setBatchErrorMessage(formError);
      return;
    }

    if (batchItems.length === 0) {
      setBatchErrorMessage("Please choose label photos.");
      return;
    }

    if (batchItems.some((item) => item.error || !item.uploadFile)) {
      setBatchErrorMessage("Please replace any photos marked with an error before verifying.");
      return;
    }

    setIsSubmittingBatch(true);
    setShowBatchServerProgress(false);
    batchProgressTimerRef.current = window.setTimeout(() => {
      setShowBatchServerProgress(true);
    }, 1000);

    try {
      const body = new FormData();
      batchItems.forEach((item) => {
        body.append("images", item.uploadFile, item.uploadFile.name);
      });
      body.append(
        "applications",
        JSON.stringify(batchItems.map((item) => cleanedFormValues(item.applicationValues))),
      );

      const response = await fetch(`${API_BASE_URL}/verify/batch`, {
        method: "POST",
        body,
      });
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(readableApiError(payload));
      }

      setBatchResult(payload);
    } catch (submitError) {
      setBatchErrorMessage(
        submitError instanceof Error
          ? submitError.message
          : "Batch verification failed. Please try again.",
      );
    } finally {
      if (batchProgressTimerRef.current) {
        window.clearTimeout(batchProgressTimerRef.current);
      }
      setShowBatchServerProgress(false);
      setIsSubmittingBatch(false);
    }
  }

  function buildFormData() {
    const body = new FormData();
    FIELD_CONFIGS.forEach((field) => {
      body.append(field.key, formValues[field.key].trim());
    });
    return body;
  }

  function validateFormFields() {
    return validateApplicationValues(formValues);
  }

  function validateBatchFormFields() {
    for (const [index, item] of batchItems.entries()) {
      const error = validateApplicationValues(item.applicationValues);

      if (error) {
        setSelectedBatchIndex(index);
        return error;
      }
    }

    return "";
  }

  function validateApplicationValues(values) {
    const missingField = FIELD_CONFIGS.find((field) => values[field.key].trim() === "");

    if (missingField) {
      return `Please enter ${missingField.label}.`;
    }

    const longField = FIELD_CONFIGS.find(
      (field) => values[field.key].trim().length > field.maxLength,
    );

    if (longField) {
      return `${longField.label} is too long. Please use ${longField.maxLength} characters or fewer.`;
    }

    return "";
  }

  function cleanedFormValues(values) {
    return Object.fromEntries(FIELD_CONFIGS.map((field) => [field.key, values[field.key].trim()]));
  }

  function clearSelectedImage() {
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl);
    }

    setImagePreviewUrl("");
    setSelectedFileName("");
    setUploadFile(null);
  }

  function clearBatchSelection() {
    batchItems.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    setBatchItems([]);
    setBatchPrepareProgress({ done: 0, total: 0 });

    if (batchFileInputRef.current) {
      batchFileInputRef.current.value = "";
    }
  }

  function startOver() {
    clearSelectedImage();
    setResult(null);
    setErrorMessage("");

    if (singleFileInputRef.current) {
      singleFileInputRef.current.value = "";
    }
  }

  function startBatchOver() {
    clearBatchSelection();
    setBatchResult(null);
    setBatchErrorMessage("");
    setSelectedBatchIndex(0);
  }

  return (
    <main className="page-shell">
      <section className="app-header" aria-labelledby="page-title">
        <p className="eyebrow">{mode === "single" ? "One label at a time" : "Batch label check"}</p>
        <h1 id="page-title">TTB Label Verification</h1>
      </section>

      <div className="mode-switch" aria-label="Verification mode">
        <button
          aria-pressed={mode === "single"}
          className={mode === "single" ? "active" : ""}
          type="button"
          onClick={() => switchMode("single")}
        >
          One Label
        </button>
        <button
          aria-pressed={mode === "batch"}
          className={mode === "batch" ? "active" : ""}
          type="button"
          onClick={() => switchMode("batch")}
        >
          Batch
        </button>
      </div>

      {mode === "single" ? (
        <>
          <form className="verification-layout" aria-busy={isBusy} onSubmit={handleSubmit}>
            <section className="photo-section" aria-labelledby="photo-heading">
              <div>
                <h2 id="photo-heading">Label Photo</h2>
                <p className="section-note">JPG, PNG, or WebP. Up to 20 MB.</p>
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
                accept="image/jpeg,image/png,image/webp"
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
                {isProcessingImage ? "Preparing the photo now." : "Checking the photo now."}
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
      ) : (
        <>
          <form className="verification-layout" aria-busy={isBatchBusy} onSubmit={handleBatchSubmit}>
            <section className="photo-section" aria-labelledby="batch-photo-heading">
              <div>
                <h2 id="batch-photo-heading">Label Photos</h2>
                <p className="section-note">JPG, PNG, or WebP. Up to 20 MB each. Up to 10 photos.</p>
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
                accept="image/jpeg,image/png,image/webp"
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
      )}
    </main>
  );
}

function FieldsSection({ formValues, isBusy, updateField }) {
  return (
    <section className="fields-section" aria-labelledby="fields-heading">
      <h2 id="fields-heading">Application Information</h2>
      <div className="field-grid">
        {FIELD_CONFIGS.map((field) => (
          <label
            className={field.type === "textarea" ? "form-field form-field-wide" : "form-field"}
            htmlFor={`field-${field.key}`}
            key={field.key}
          >
            <span>{field.label}</span>
            {field.type === "textarea" ? (
              <textarea
                id={`field-${field.key}`}
                disabled={isBusy}
                maxLength={field.maxLength}
                required
                rows={5}
                value={formValues[field.key]}
                onChange={(event) => updateField(field.key, event.target.value)}
              />
            ) : (
              <input
                id={`field-${field.key}`}
                disabled={isBusy}
                maxLength={field.maxLength}
                required
                type="text"
                value={formValues[field.key]}
                onChange={(event) => updateField(field.key, event.target.value)}
              />
            )}
          </label>
        ))}
      </div>
    </section>
  );
}

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

function labelForField(fieldName) {
  return FIELD_CONFIGS.find((field) => field.key === fieldName)?.label || fieldName;
}

function failureReason(field) {
  const extracted = typeof field.found === "string" ? field.found.trim() : "";
  const message = field.message?.toLowerCase() || "";

  if (!extracted || message.includes("missing")) {
    return "Missing on label";
  }

  if (message.includes("could not parse")) {
    return "Could not read clearly";
  }

  return "Does not match";
}

function statusLabel(status) {
  if (status === "APPROVED") {
    return "APPROVED";
  }

  if (status === "NEEDS_REVIEW") {
    return "NEEDS REVIEW";
  }

  return "ERROR";
}

function statusClass(status) {
  if (status === "APPROVED") {
    return "approved";
  }

  if (status === "NEEDS_REVIEW") {
    return "review";
  }

  return "error";
}

function formatSeconds(latencyMs) {
  if (typeof latencyMs !== "number") {
    return "";
  }

  return (latencyMs / 1000).toFixed(1);
}

function displayValue(value) {
  if (typeof value !== "string" || value.trim() === "") {
    return "Nothing found";
  }

  return value;
}

function readableApiError(payload) {
  return payload?.error?.message || "Verification failed. Please try again.";
}

function validateOriginalFile(file) {
  if (!SUPPORTED_IMAGE_TYPES.includes(file.type)) {
    return "Please choose a JPG, PNG, or WebP photo.";
  }

  if (file.size > MAX_ORIGINAL_BYTES) {
    return "Please choose a photo up to 20 MB.";
  }

  return "";
}

async function prepareImageForUpload(file) {
  const image = await loadImage(file);
  const attempts = [
    { edge: MAX_IMAGE_EDGE, quality: JPEG_QUALITY },
    { edge: MAX_IMAGE_EDGE, quality: MIN_JPEG_QUALITY },
    { edge: 1440, quality: MIN_JPEG_QUALITY },
    { edge: 1280, quality: MIN_JPEG_QUALITY },
    { edge: 1120, quality: MIN_JPEG_QUALITY },
  ];

  for (const attempt of attempts) {
    const blob = await renderImageToJpeg(image, attempt.edge, attempt.quality);

    if (blob.size <= MAX_UPLOAD_BYTES) {
      const outputName = file.name.replace(/\.[^.]+$/, "") || "label-photo";
      return new File([blob], `${outputName}.jpg`, { type: "image/jpeg" });
    }
  }

  throw new Error("That photo is still too large after resizing. Please take a closer, clearer photo and try again.");
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();

    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("We could not read that photo. Please choose a clear label photo."));
    };
    image.src = objectUrl;
  });
}

function renderImageToJpeg(image, maxEdge, quality) {
  const scale = Math.min(1, maxEdge / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("We could not prepare that photo. Please try another label photo.");
  }

  context.drawImage(image, 0, 0, width, height);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("We could not prepare that photo. Please try another label photo."));
          return;
        }

        resolve(blob);
      },
      "image/jpeg",
      quality,
    );
  });
}

export default App;
