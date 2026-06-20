import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

const MAX_ORIGINAL_BYTES = 20 * 1024 * 1024;
const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_EDGE = 1600;
const JPEG_QUALITY = 0.85;
const MIN_JPEG_QUALITY = 0.82;
const SUPPORTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

const STANDARD_WARNING =
  "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS.";

const FIELD_CONFIGS = [
  { key: "brand_name", label: "Brand Name", type: "input" },
  { key: "product_class", label: "Product Type", type: "input" },
  { key: "producer_name", label: "Producer Name", type: "input" },
  { key: "country_of_origin", label: "Country of Origin", type: "input" },
  { key: "alcohol_by_volume", label: "Alcohol by Volume", type: "input" },
  { key: "net_contents", label: "Net Contents", type: "input" },
  { key: "government_warning", label: "Government Warning", type: "textarea" },
];

const INITIAL_FORM = {
  brand_name: "",
  product_class: "",
  producer_name: "",
  country_of_origin: "",
  alcohol_by_volume: "",
  net_contents: "",
  government_warning: STANDARD_WARNING,
};

function App() {
  const fileInputRef = useRef(null);
  const [formValues, setFormValues] = useState(INITIAL_FORM);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [imagePreviewUrl, setImagePreviewUrl] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [isProcessingImage, setIsProcessingImage] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState(null);

  const isBusy = isProcessingImage || isSubmitting;
  const verdictLabel = result?.verdict === "PASS" ? "APPROVED" : "NEEDS REVIEW";
  const checkedSeconds = useMemo(() => {
    if (!result || typeof result.latency_ms !== "number") {
      return "";
    }

    return (result.latency_ms / 1000).toFixed(1);
  }, [result]);

  useEffect(() => {
    return () => {
      if (imagePreviewUrl) {
        URL.revokeObjectURL(imagePreviewUrl);
      }
    };
  }, [imagePreviewUrl]);

  function updateField(field, value) {
    setFormValues((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleImageChange(event) {
    const file = event.target.files?.[0];
    setErrorMessage("");
    setResult(null);
    clearSelectedImage();

    if (!file) {
      return;
    }

    if (!SUPPORTED_IMAGE_TYPES.includes(file.type)) {
      setErrorMessage("Please choose a JPG, PNG, or WebP photo.");
      event.target.value = "";
      return;
    }

    if (file.size > MAX_ORIGINAL_BYTES) {
      setErrorMessage("Please choose a photo up to 20 MB.");
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

  async function handleSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setResult(null);

    const missingField = FIELD_CONFIGS.find((field) => formValues[field.key].trim() === "");

    if (!uploadFile) {
      setErrorMessage("Please choose a label photo.");
      return;
    }

    if (missingField) {
      setErrorMessage(`Please enter ${missingField.label}.`);
      return;
    }

    setIsSubmitting(true);

    try {
      const body = new FormData();
      body.append("image", uploadFile);

      FIELD_CONFIGS.forEach((field) => {
        body.append(field.key, formValues[field.key].trim());
      });

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

  function clearSelectedImage() {
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl);
    }

    setImagePreviewUrl("");
    setSelectedFileName("");
    setUploadFile(null);
  }

  function startOver() {
    clearSelectedImage();
    setFormValues(INITIAL_FORM);
    setResult(null);
    setErrorMessage("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  return (
    <main className="page-shell">
      <section className="app-header" aria-labelledby="page-title">
        <p className="eyebrow">One label at a time</p>
        <h1 id="page-title">TTB Label Verification</h1>
      </section>

      <form className="verification-layout" onSubmit={handleSubmit}>
        <section className="photo-section" aria-labelledby="photo-heading">
          <div>
            <h2 id="photo-heading">Label Photo</h2>
            <p className="section-note">JPG, PNG, or WebP. Up to 20 MB.</p>
          </div>

          <button
            className="file-button"
            disabled={isBusy}
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            Choose Label Photo
          </button>
          <input
            ref={fileInputRef}
            className="file-input"
            type="file"
            accept="image/jpeg,image/png,image/webp"
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

        <section className="fields-section" aria-labelledby="fields-heading">
          <h2 id="fields-heading">Application Information</h2>
          <div className="field-grid">
            {FIELD_CONFIGS.map((field) => (
              <label
                className={field.type === "textarea" ? "form-field form-field-wide" : "form-field"}
                key={field.key}
              >
                <span>{field.label}</span>
                {field.type === "textarea" ? (
                  <textarea
                    disabled={isBusy}
                    rows={5}
                    value={formValues[field.key]}
                    onChange={(event) => updateField(field.key, event.target.value)}
                  />
                ) : (
                  <input
                    disabled={isBusy}
                    type="text"
                    value={formValues[field.key]}
                    onChange={(event) => updateField(field.key, event.target.value)}
                  />
                )}
              </label>
            ))}
          </div>
        </section>

        {errorMessage ? (
          <div className="alert" role="alert">
            {errorMessage}
          </div>
        ) : null}

        {isBusy ? (
          <div className="status-band" aria-live="polite">
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
        <section className="results-section" aria-labelledby="results-heading" aria-live="polite">
          <div className={`verdict-band ${result.verdict === "PASS" ? "approved" : "review"}`}>
            <p>Result</p>
            <h2 id="results-heading">{verdictLabel}</h2>
            {checkedSeconds ? <span>Checked in {checkedSeconds} seconds</span> : null}
          </div>

          <div className="results-list">
            {result.fields.map((field) => (
              <ResultRow field={field} key={field.field} />
            ))}
          </div>
        </section>
      ) : null}
    </main>
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
        <div className="comparison-grid">
          <div>
            <span>Application Says</span>
            <p>{displayValue(field.expected)}</p>
          </div>
          <div>
            <span>Found on Label</span>
            <p>{displayValue(field.extracted)}</p>
          </div>
        </div>
      ) : null}
    </article>
  );
}

function labelForField(fieldName) {
  return FIELD_CONFIGS.find((field) => field.key === fieldName)?.label || fieldName;
}

function failureReason(field) {
  const extracted = typeof field.extracted === "string" ? field.extracted.trim() : "";
  const message = field.message?.toLowerCase() || "";

  if (!extracted || message.includes("missing")) {
    return "Missing on label";
  }

  if (message.includes("could not parse")) {
    return "Could not read clearly";
  }

  return "Does not match";
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
