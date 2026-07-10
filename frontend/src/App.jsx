import { useEffect, useMemo, useRef, useState } from "react";

import BatchFlow from "./components/BatchFlow.jsx";
import SingleFlow from "./components/SingleFlow.jsx";
import { formatSeconds, readableApiError } from "./lib/display.js";
import {
  COLD_START_HINT,
  INITIAL_FORM,
  MAX_BATCH_IMAGES,
  cleanedFormValues,
  validateApplicationValues,
} from "./lib/formConfig.js";
import { prepareImageForUpload, validateOriginalFile } from "./lib/image.js";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

function App() {
  const singleFileInputRef = useRef(null);
  const batchFileInputRef = useRef(null);
  const singleColdStartTimerRef = useRef(null);
  const batchProgressTimerRef = useRef(null);
  const batchColdStartTimerRef = useRef(null);
  const singleErrorRef = useRef(null);
  const batchErrorRef = useRef(null);
  const [mode, setMode] = useState("single");
  const [formValues, setFormValues] = useState(INITIAL_FORM);

  const [selectedFileName, setSelectedFileName] = useState("");
  const [imagePreviewUrl, setImagePreviewUrl] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [isProcessingImage, setIsProcessingImage] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showSingleColdStartHint, setShowSingleColdStartHint] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState(null);

  const [batchItems, setBatchItems] = useState([]);
  const [batchPrepareProgress, setBatchPrepareProgress] = useState({ done: 0, total: 0 });
  const [isPreparingBatch, setIsPreparingBatch] = useState(false);
  const [isSubmittingBatch, setIsSubmittingBatch] = useState(false);
  const [showBatchServerProgress, setShowBatchServerProgress] = useState(false);
  const [showBatchColdStartHint, setShowBatchColdStartHint] = useState(false);
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
      clearSingleColdStartTimer();
      clearBatchTimers();
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
    clearSingleColdStartTimer();
    clearBatchTimers();
    setMode(nextMode);
    setErrorMessage("");
    setBatchErrorMessage("");
    setShowSingleColdStartHint(false);
    setShowBatchColdStartHint(false);
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

    const formError = validateApplicationValues(formValues);
    if (formError) {
      setErrorMessage(formError);
      return;
    }

    if (!uploadFile) {
      setErrorMessage("Please choose a label photo.");
      return;
    }

    setIsSubmitting(true);
    startSingleColdStartTimer();

    try {
      const body = new FormData();
      const cleanedValues = cleanedFormValues(formValues);
      Object.entries(cleanedValues).forEach(([field, value]) => body.append(field, value));
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
      clearSingleColdStartTimer();
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
    setShowBatchColdStartHint(false);
    startBatchTimers();

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
      clearBatchTimers();
      setShowBatchServerProgress(false);
      setIsSubmittingBatch(false);
    }
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
    setShowSingleColdStartHint(false);

    if (singleFileInputRef.current) {
      singleFileInputRef.current.value = "";
    }
  }

  function startBatchOver() {
    clearBatchSelection();
    setBatchResult(null);
    setBatchErrorMessage("");
    setSelectedBatchIndex(0);
    setShowBatchColdStartHint(false);
  }

  function startSingleColdStartTimer() {
    setShowSingleColdStartHint(false);
    clearSingleColdStartTimer();
    singleColdStartTimerRef.current = window.setTimeout(() => {
      setShowSingleColdStartHint(true);
    }, 2000);
  }

  function clearSingleColdStartTimer() {
    if (singleColdStartTimerRef.current) {
      window.clearTimeout(singleColdStartTimerRef.current);
      singleColdStartTimerRef.current = null;
    }
  }

  function startBatchTimers() {
    clearBatchTimers();
    batchProgressTimerRef.current = window.setTimeout(() => {
      setShowBatchServerProgress(true);
    }, 1000);
    batchColdStartTimerRef.current = window.setTimeout(() => {
      setShowBatchServerProgress(true);
      setShowBatchColdStartHint(true);
    }, 2000);
  }

  function clearBatchTimers() {
    if (batchProgressTimerRef.current) {
      window.clearTimeout(batchProgressTimerRef.current);
      batchProgressTimerRef.current = null;
    }

    if (batchColdStartTimerRef.current) {
      window.clearTimeout(batchColdStartTimerRef.current);
      batchColdStartTimerRef.current = null;
    }
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
        <SingleFlow
          checkedSeconds={checkedSeconds}
          coldStartHint={showSingleColdStartHint ? COLD_START_HINT : ""}
          errorMessage={errorMessage}
          formValues={formValues}
          handleImageChange={handleImageChange}
          handleSubmit={handleSubmit}
          imagePreviewUrl={imagePreviewUrl}
          isBusy={isBusy}
          isProcessingImage={isProcessingImage}
          isSubmitting={isSubmitting}
          result={result}
          selectedFileName={selectedFileName}
          singleErrorRef={singleErrorRef}
          singleFileInputRef={singleFileInputRef}
          startOver={startOver}
          updateField={updateField}
          verdictLabel={verdictLabel}
        />
      ) : (
        <BatchFlow
          batchErrorMessage={batchErrorMessage}
          batchErrorRef={batchErrorRef}
          batchFileInputRef={batchFileInputRef}
          batchItems={batchItems}
          batchPrepareProgress={batchPrepareProgress}
          batchResult={batchResult}
          batchSeconds={batchSeconds}
          coldStartHint={showBatchColdStartHint ? COLD_START_HINT : ""}
          handleBatchFilesChange={handleBatchFilesChange}
          handleBatchSubmit={handleBatchSubmit}
          isBatchBusy={isBatchBusy}
          isPreparingBatch={isPreparingBatch}
          isSubmittingBatch={isSubmittingBatch}
          selectedBatchFormItem={selectedBatchFormItem}
          selectedBatchIndex={selectedBatchIndex}
          selectedBatchResultItem={selectedBatchResultItem}
          setSelectedBatchIndex={setSelectedBatchIndex}
          showBatchServerProgress={showBatchServerProgress}
          startBatchOver={startBatchOver}
          updateBatchItemField={updateBatchItemField}
        />
      )}
    </main>
  );
}

export default App;
