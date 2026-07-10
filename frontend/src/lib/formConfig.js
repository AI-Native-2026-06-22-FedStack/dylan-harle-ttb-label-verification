export const STANDARD_WARNING =
  "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS.";

export const FIELD_CONFIGS = [
  { key: "brand_name", label: "Brand Name", inputKind: "text", maxLength: 160 },
  { key: "class_type", label: "Product Type", inputKind: "text", maxLength: 160 },
  { key: "producer", label: "Producer Name", inputKind: "text", maxLength: 200 },
  { key: "country_of_origin", label: "Country of Origin", inputKind: "text", maxLength: 120 },
  {
    key: "abv",
    label: "Alcohol by Volume",
    inputKind: "number",
    maxLength: 80,
    min: "0",
    step: "0.1",
  },
  {
    key: "net_contents",
    label: "Net Contents (mL)",
    inputKind: "number",
    maxLength: 80,
    min: "0",
    step: "0.01",
    submitSuffix: "mL",
  },
  { key: "government_warning", label: "Government Warning", inputKind: "textarea", maxLength: 650 },
];

export const INITIAL_FORM = {
  brand_name: "",
  class_type: "",
  producer: "",
  country_of_origin: "",
  abv: "",
  net_contents: "",
  government_warning: STANDARD_WARNING,
};

export const MAX_BATCH_IMAGES = 10;
export const COLD_START_HINT = "First request may take a few extra seconds while the server wakes up.";

export function validateApplicationValues(values) {
  const missingField = FIELD_CONFIGS.find((field) => values[field.key].trim() === "");

  if (missingField) {
    return `Please enter ${missingField.label}.`;
  }

  const invalidNumberField = FIELD_CONFIGS.find((field) => {
    if (field.inputKind !== "number") {
      return false;
    }

    const numericValue = Number(values[field.key]);
    return !Number.isFinite(numericValue) || numericValue < 0;
  });

  if (invalidNumberField) {
    return `Please enter a valid ${invalidNumberField.label}.`;
  }

  const longField = FIELD_CONFIGS.find(
    (field) => values[field.key].trim().length > field.maxLength,
  );

  if (longField) {
    return `${longField.label} is too long. Please use ${longField.maxLength} characters or fewer.`;
  }

  return "";
}

export function cleanedFormValues(values) {
  return Object.fromEntries(
    FIELD_CONFIGS.map((field) => [field.key, submittedFieldValue(field, values[field.key])]),
  );
}

function submittedFieldValue(field, value) {
  const trimmedValue = value.trim();

  if (field.submitSuffix && trimmedValue !== "") {
    return `${trimmedValue} ${field.submitSuffix}`;
  }

  return trimmedValue;
}
