const MAX_ORIGINAL_BYTES = 20 * 1024 * 1024;
const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_EDGE = 1280;
const JPEG_QUALITY = 0.85;
const MIN_JPEG_QUALITY = 0.82;

export function validateOriginalFile(file) {
  if (file.size > MAX_ORIGINAL_BYTES) {
    return "Please choose a photo up to 20 MB.";
  }

  return "";
}

export async function prepareImageForUpload(file) {
  let image;

  try {
    image = await loadImage(file);
  } catch (error) {
    if (isHeifUpload(file) && file.size <= MAX_UPLOAD_BYTES) {
      return file;
    }

    if (isHeifUpload(file)) {
      throw new Error(
        "We could not prepare that HEIC/HEIF photo in this browser. Please choose one under 2 MB or convert it to JPEG.",
      );
    }

    throw error;
  }

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

function isHeifUpload(file) {
  const fileType = (file.type || "").toLowerCase();
  const fileName = (file.name || "").toLowerCase();

  return (
    fileType === "image/heic" ||
    fileType === "image/heif" ||
    fileName.endsWith(".heic") ||
    fileName.endsWith(".heif")
  );
}

export function loadImage(file) {
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

export function renderImageToJpeg(image, maxEdge, quality) {
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
