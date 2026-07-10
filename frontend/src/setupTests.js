import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";

const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;
const originalImage = globalThis.Image;
const originalGetContext = HTMLCanvasElement.prototype.getContext;
const originalToBlob = HTMLCanvasElement.prototype.toBlob;

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:label-preview");
  URL.revokeObjectURL = vi.fn();

  globalThis.Image = class MockImage {
    constructor() {
      this.naturalWidth = 640;
      this.naturalHeight = 480;
    }

    set src(_value) {
      queueMicrotask(() => this.onload?.());
    }
  };

  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    drawImage: vi.fn(),
  }));
  HTMLCanvasElement.prototype.toBlob = vi.fn((callback) => {
    callback(new Blob(["processed image"], { type: "image/jpeg" }));
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  globalThis.Image = originalImage;
  HTMLCanvasElement.prototype.getContext = originalGetContext;
  HTMLCanvasElement.prototype.toBlob = originalToBlob;
});
