import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import App from "./App.jsx";

const SUCCESS_RESPONSE = {
  overall_verdict: "APPROVED",
  results: [
    {
      field: "brand_name",
      status: "PASS",
      expected: "Acme Cellars",
      found: "ACME CELLARS",
      match_type: "fuzzy_token_set_ratio",
      score: 100,
      message: "Fuzzy score 100.00; threshold 90.00.",
    },
  ],
  latency_ms: 1200,
};

const FIELD_VALUES = {
  brand_name: "  Acme Cellars  ",
  class_type: "Red Wine",
  producer: "Acme Winery LLC",
  country_of_origin: "United States",
  abv: "13.5",
  net_contents: "750",
};

describe("App", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => SUCCESS_RESPONSE,
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test("renders the single-label file input and all seven application fields", () => {
    render(<App />);

    const fileInput = screen.getByLabelText(/choose one label photo/i);
    const abvInput = screen.getByLabelText(/alcohol by volume/i);
    const netContentsInput = screen.getByLabelText(/net contents/i);

    expect(fileInput).toBeInTheDocument();
    expect(fileInput).toHaveAttribute("accept", "image/*");
    expect(screen.getByLabelText(/brand name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/product type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/producer name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/country of origin/i)).toBeInTheDocument();
    expect(abvInput).toHaveAttribute("type", "number");
    expect(abvInput).toHaveAttribute("min", "0");
    expect(abvInput).toHaveAttribute("step", "0.1");
    expect(netContentsInput).toHaveAttribute("type", "number");
    expect(netContentsInput).toHaveAttribute("min", "0");
    expect(netContentsInput).toHaveAttribute("step", "0.01");
    expect(screen.getByLabelText(/government warning/i)).toBeInTheDocument();
  });

  test("renders the batch file input with broad image accept", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /batch/i }));

    expect(screen.getByLabelText(/choose label photos for batch verification/i)).toHaveAttribute(
      "accept",
      "image/*",
    );
  });

  test("submits one image plus the seven application fields to the verify endpoint", async () => {
    const user = userEvent.setup();
    render(<App />);

    const file = new File(["label image"], "label.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText(/choose one label photo/i), file);
    await screen.findByText(/photo ready/i);

    await user.type(screen.getByLabelText(/brand name/i), FIELD_VALUES.brand_name);
    await user.type(screen.getByLabelText(/product type/i), FIELD_VALUES.class_type);
    await user.type(screen.getByLabelText(/producer name/i), FIELD_VALUES.producer);
    await user.type(screen.getByLabelText(/country of origin/i), FIELD_VALUES.country_of_origin);
    await user.type(screen.getByLabelText(/alcohol by volume/i), FIELD_VALUES.abv);
    await user.type(screen.getByLabelText(/net contents/i), FIELD_VALUES.net_contents);

    await user.click(screen.getByRole("button", { name: /verify label/i }));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const [url, options] = fetch.mock.calls[0];
    const body = options.body;

    expect(url).toBe("http://localhost:8000/verify");
    expect(options.method).toBe("POST");
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("image")).toBeInstanceOf(File);
    expect(body.get("image").name).toBe("label.jpg");
    expect(body.get("brand_name")).toBe("Acme Cellars");
    expect(body.get("class_type")).toBe(FIELD_VALUES.class_type);
    expect(body.get("producer")).toBe(FIELD_VALUES.producer);
    expect(body.get("country_of_origin")).toBe(FIELD_VALUES.country_of_origin);
    expect(body.get("abv")).toBe(FIELD_VALUES.abv);
    expect(body.get("net_contents")).toBe(`${FIELD_VALUES.net_contents} mL`);
    expect(body.get("government_warning")).toMatch(/^GOVERNMENT WARNING:/);
    expect(await screen.findByRole("heading", { name: "APPROVED" })).toBeInTheDocument();
  });

  test("sends small HEIC files directly when browser decoding fails", async () => {
    const user = userEvent.setup();
    globalThis.Image = class MockFailingImage {
      set src(_value) {
        queueMicrotask(() => this.onerror?.());
      }
    };
    render(<App />);

    const file = new File(["heic image"], "label.heic", { type: "image/heic" });
    await user.upload(screen.getByLabelText(/choose one label photo/i), file);
    await screen.findByText(/photo ready/i);
    await user.type(screen.getByLabelText(/brand name/i), FIELD_VALUES.brand_name);
    await user.type(screen.getByLabelText(/product type/i), FIELD_VALUES.class_type);
    await user.type(screen.getByLabelText(/producer name/i), FIELD_VALUES.producer);
    await user.type(screen.getByLabelText(/country of origin/i), FIELD_VALUES.country_of_origin);
    await user.type(screen.getByLabelText(/alcohol by volume/i), FIELD_VALUES.abv);
    await user.type(screen.getByLabelText(/net contents/i), FIELD_VALUES.net_contents);

    await user.click(screen.getByRole("button", { name: /verify label/i }));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const body = fetch.mock.calls[0][1].body;

    expect(body.get("image")).toBeInstanceOf(File);
    expect(body.get("image").name).toBe("label.heic");
    expect(body.get("image").type).toBe("image/heic");
  });

  test("shows a cold-start hint when a single-label request takes longer than two seconds", async () => {
    const user = userEvent.setup();
    let resolveFetch;
    globalThis.fetch = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFetch = () =>
            resolve({
              ok: true,
              json: async () => SUCCESS_RESPONSE,
            });
        }),
    );
    render(<App />);

    const file = new File(["label image"], "label.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText(/choose one label photo/i), file);
    await screen.findByText(/photo ready/i);
    await user.type(screen.getByLabelText(/brand name/i), FIELD_VALUES.brand_name);
    await user.type(screen.getByLabelText(/product type/i), FIELD_VALUES.class_type);
    await user.type(screen.getByLabelText(/producer name/i), FIELD_VALUES.producer);
    await user.type(screen.getByLabelText(/country of origin/i), FIELD_VALUES.country_of_origin);
    await user.type(screen.getByLabelText(/alcohol by volume/i), FIELD_VALUES.abv);
    await user.type(screen.getByLabelText(/net contents/i), FIELD_VALUES.net_contents);

    await user.click(screen.getByRole("button", { name: /verify label/i }));

    expect(
      await screen.findByText(/first request may take a few extra seconds/i, {}, { timeout: 3000 }),
    ).toBeInTheDocument();

    resolveFetch();
    await screen.findByRole("heading", { name: "APPROVED" });
  }, 10000);
});
