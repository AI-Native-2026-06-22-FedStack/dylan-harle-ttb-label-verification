import { FIELD_CONFIGS } from "../lib/formConfig.js";

function FieldsSection({ formValues, isBusy, updateField }) {
  return (
    <section className="fields-section" aria-labelledby="fields-heading">
      <h2 id="fields-heading">Application Information</h2>
      <div className="field-grid">
        {FIELD_CONFIGS.map((field) => (
          <label
            className={field.inputKind === "textarea" ? "form-field form-field-wide" : "form-field"}
            htmlFor={`field-${field.key}`}
            key={field.key}
          >
            <span>{field.label}</span>
            {field.inputKind === "textarea" ? (
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
                max={field.max}
                maxLength={field.inputKind === "number" ? undefined : field.maxLength}
                min={field.min}
                required
                step={field.step}
                type={field.inputKind === "number" ? "number" : "text"}
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

export default FieldsSection;
