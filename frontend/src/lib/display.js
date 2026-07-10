import { FIELD_CONFIGS } from "./formConfig.js";

export function labelForField(fieldName) {
  return FIELD_CONFIGS.find((field) => field.key === fieldName)?.label || fieldName;
}

export function failureReason(field) {
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

export function statusLabel(status) {
  if (status === "APPROVED") {
    return "APPROVED";
  }

  if (status === "NEEDS_REVIEW") {
    return "NEEDS REVIEW";
  }

  return "ERROR";
}

export function statusClass(status) {
  if (status === "APPROVED") {
    return "approved";
  }

  if (status === "NEEDS_REVIEW") {
    return "review";
  }

  return "error";
}

export function formatSeconds(latencyMs) {
  if (typeof latencyMs !== "number") {
    return "";
  }

  return (latencyMs / 1000).toFixed(1);
}

export function displayValue(value) {
  if (typeof value !== "string" || value.trim() === "") {
    return "Nothing found";
  }

  return value;
}

export function readableApiError(payload) {
  return payload?.error?.message || "Verification failed. Please try again.";
}
