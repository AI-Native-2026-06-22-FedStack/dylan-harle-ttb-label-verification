import base64
import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, ValidationError

from app.models import ExtractedLabel


DEFAULT_VISION_MODEL = "gpt-5.4-mini"
DEFAULT_IMAGE_DETAIL = "high"
DEFAULT_MAX_LONG_EDGE = 1280
DEFAULT_JPEG_QUALITY = 85
MIN_JPEG_QUALITY = 82
DEFAULT_MAX_PROCESSED_BYTES = 2 * 1024 * 1024
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 3.8
DEFAULT_MAX_IMAGE_PIXELS = 20_000_000
SUPPORTED_IMAGE_DETAILS = {"auto", "high", "low", "original"}

logger = logging.getLogger(__name__)


VISION_SYSTEM_PROMPT = (
    "You extract visible text from alcohol beverage label photos for TTB label "
    "verification. Return structured data only."
)

VISION_EXTRACTION_PROMPT = """
Extract only these fields from visible alcohol beverage label text:
- brand_name
- class_type
- producer
- country_of_origin
- abv
- net_contents
- government_warning
- raw_text
- extraction_confidence

Rules:
- Use only text visible in the image.
- Return null for any field that is missing, unreadable, ambiguous, obscured, blurry,
  cropped, angled beyond reliable reading, or not present because the image is not a
  beverage label.
- Never infer, normalize, autocorrect, expand abbreviations, or complete missing text
  from memory or outside knowledge.
- For government_warning, copy the warning exactly and verbatim as visible. Preserve
  case, punctuation, wording, and spacing as much as the image allows.
- If the government warning is only partly readable, return only confidently visible
  text or null; never fill gaps.
- For raw_text, return the visible label text you relied on, without inventing text.
- For extraction_confidence, return a number from 0.0 to 1.0 for the overall extraction.
""".strip()


class VisionServiceError(Exception):
    """Base exception for vision extraction failures."""


class VisionConfigurationError(VisionServiceError):
    """Raised when the configured vision provider cannot be initialized."""


class VisionInputError(VisionServiceError):
    """Raised when image bytes cannot be decoded or processed."""


class VisionProviderError(VisionServiceError):
    """Raised when the provider request fails before a parseable response exists."""


class VisionTimeoutError(VisionProviderError):
    """Raised when the provider request times out."""


class VisionParseError(VisionServiceError):
    """Raised when provider output does not match the extraction schema."""


class VisionService(Protocol):
    def extract(self, image_bytes: bytes, content_type: str | None = None) -> ExtractedLabel:
        """Extract label fields from a single image."""


class VisionExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str | None
    class_type: str | None
    producer: str | None
    country_of_origin: str | None
    abv: str | None
    net_contents: str | None
    government_warning: str | None
    raw_text: str | None
    extraction_confidence: float | None

    def to_extracted_label(self) -> ExtractedLabel:
        return ExtractedLabel(**self.model_dump())


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    content_type: str
    width: int
    height: int


class FakeVisionService:
    def __init__(
        self,
        result: ExtractedLabel | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or ExtractedLabel()
        self.error = error
        self.calls: list[tuple[bytes, str | None]] = []

    def extract(self, image_bytes: bytes, content_type: str | None = None) -> ExtractedLabel:
        self.calls.append((image_bytes, content_type))

        if self.error is not None:
            raise self.error

        return self.result


def preprocess_label_image(
    image_bytes: bytes,
    *,
    max_long_edge: int = DEFAULT_MAX_LONG_EDGE,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    min_jpeg_quality: int = MIN_JPEG_QUALITY,
    max_output_bytes: int = DEFAULT_MAX_PROCESSED_BYTES,
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
) -> ProcessedImage:
    if not image_bytes:
        raise VisionInputError("Image is empty.")

    if max_long_edge <= 0:
        raise ValueError("max_long_edge must be positive.")

    if max_output_bytes <= 0:
        raise ValueError("max_output_bytes must be positive.")

    if max_pixels <= 0:
        raise ValueError("max_pixels must be positive.")

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            transposed_image = ImageOps.exif_transpose(image)
            pixel_count = transposed_image.width * transposed_image.height

            if pixel_count > max_pixels:
                raise VisionInputError(
                    f"Image has {pixel_count} pixels, above the {max_pixels} pixel cap."
                )

            rgb_image = transposed_image.convert("RGB")
            rgb_image.load()
    except VisionInputError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise VisionInputError("Image bytes could not be decoded.") from exc

    target_edges = _target_long_edges(rgb_image, max_long_edge)
    qualities = _jpeg_quality_steps(jpeg_quality, min_jpeg_quality)
    last_processed: ProcessedImage | None = None

    for edge in target_edges:
        resized = _resize_to_long_edge(rgb_image, edge)

        for quality in qualities:
            data = _encode_jpeg(resized, quality)
            processed = ProcessedImage(
                data=data,
                content_type="image/jpeg",
                width=resized.width,
                height=resized.height,
            )
            last_processed = processed

            if len(data) <= max_output_bytes:
                return processed

    size = len(last_processed.data) if last_processed is not None else len(image_bytes)
    raise VisionInputError(
        f"Processed image is {size} bytes, above the {max_output_bytes} byte cap."
    )


class OpenAIVisionService:
    def __init__(
        self,
        *,
        client: object,
        model: str = DEFAULT_VISION_MODEL,
        image_detail: str = DEFAULT_IMAGE_DETAIL,
        timeout_seconds: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        max_long_edge: int = DEFAULT_MAX_LONG_EDGE,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        min_jpeg_quality: int = MIN_JPEG_QUALITY,
        max_processed_bytes: int = DEFAULT_MAX_PROCESSED_BYTES,
        max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    ) -> None:
        self._client = client
        self.model = model
        self.image_detail = image_detail
        self.timeout_seconds = timeout_seconds
        self.max_long_edge = max_long_edge
        self.jpeg_quality = jpeg_quality
        self.min_jpeg_quality = min_jpeg_quality
        self.max_processed_bytes = max_processed_bytes
        self.max_image_pixels = max_image_pixels

    @classmethod
    def from_env(cls) -> "OpenAIVisionService":
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_VISION_MODEL")

        if not api_key:
            raise VisionConfigurationError("OPENAI_API_KEY is not set.")

        if model is None or model.strip() == "":
            raise VisionConfigurationError("OPENAI_VISION_MODEL is not set.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise VisionConfigurationError("The openai package is not installed.") from exc

        return cls(
            client=OpenAI(api_key=api_key),
            model=model.strip(),
            image_detail=_env_image_detail("OPENAI_IMAGE_DETAIL", DEFAULT_IMAGE_DETAIL),
            timeout_seconds=_env_float(
                "OPENAI_VISION_TIMEOUT_SECONDS",
                DEFAULT_PROVIDER_TIMEOUT_SECONDS,
                minimum=0.5,
                maximum=30.0,
            ),
            max_long_edge=_env_int(
                "OPENAI_MAX_IMAGE_LONG_EDGE",
                DEFAULT_MAX_LONG_EDGE,
                minimum=320,
                maximum=2400,
            ),
            jpeg_quality=_env_int(
                "OPENAI_JPEG_QUALITY",
                DEFAULT_JPEG_QUALITY,
                minimum=50,
                maximum=95,
            ),
            min_jpeg_quality=_env_int(
                "OPENAI_MIN_JPEG_QUALITY",
                MIN_JPEG_QUALITY,
                minimum=40,
                maximum=95,
            ),
            max_processed_bytes=_env_int(
                "OPENAI_MAX_PROCESSED_BYTES",
                DEFAULT_MAX_PROCESSED_BYTES,
                minimum=128 * 1024,
                maximum=4 * 1024 * 1024,
            ),
            max_image_pixels=_env_int(
                "OPENAI_MAX_IMAGE_PIXELS",
                DEFAULT_MAX_IMAGE_PIXELS,
                minimum=1_000_000,
                maximum=40_000_000,
            ),
        )

    def extract(self, image_bytes: bytes, content_type: str | None = None) -> ExtractedLabel:
        extraction_start = time.perf_counter()
        preprocess_start = time.perf_counter()
        processed = preprocess_label_image(
            image_bytes,
            max_long_edge=self.max_long_edge,
            jpeg_quality=self.jpeg_quality,
            min_jpeg_quality=self.min_jpeg_quality,
            max_output_bytes=self.max_processed_bytes,
            max_pixels=self.max_image_pixels,
        )
        preprocess_ms = _elapsed_ms(preprocess_start)
        image_url = _data_url(processed)

        try:
            provider_start = time.perf_counter()
            response = self._client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": VISION_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": VISION_EXTRACTION_PROMPT,
                            },
                            {
                                "type": "input_image",
                                "image_url": image_url,
                                "detail": self.image_detail,
                            },
                        ],
                    },
                ],
                text_format=VisionExtraction,
                timeout=self.timeout_seconds,
            )
            provider_ms = _elapsed_ms(provider_start)
        except (ValidationError, ValueError) as exc:
            raise VisionParseError(
                "Vision model returned output that did not match the extraction schema."
            ) from exc
        except TimeoutError as exc:
            raise VisionTimeoutError("Vision model request timed out.") from exc
        except Exception as exc:
            if _is_timeout_error(exc):
                raise VisionTimeoutError("Vision model request timed out.") from exc

            raise VisionProviderError("Vision model request failed.") from exc

        label = _extract_parsed_label(response)
        logger.info(
            "vision extraction completed model=%s detail=%s original_bytes=%s "
            "processed_bytes=%s processed_width=%s processed_height=%s "
            "preprocess_ms=%s provider_ms=%s total_ms=%s",
            self.model,
            self.image_detail,
            len(image_bytes),
            len(processed.data),
            processed.width,
            processed.height,
            preprocess_ms,
            provider_ms,
            _elapsed_ms(extraction_start),
        )
        return label


@lru_cache(maxsize=1)
def get_openai_vision_service_from_env() -> OpenAIVisionService:
    return OpenAIVisionService.from_env()


def _extract_parsed_label(response: object) -> ExtractedLabel:
    parsed = getattr(response, "output_parsed", None)

    if parsed is None:
        raise VisionParseError("Vision response did not include parsed output.")

    try:
        extraction = (
            parsed
            if isinstance(parsed, VisionExtraction)
            else VisionExtraction.model_validate(parsed)
        )
    except ValidationError as exc:
        raise VisionParseError(
            "Vision model returned output that did not match the extraction schema."
        ) from exc

    return extraction.to_extracted_label()


def _data_url(processed: ProcessedImage) -> str:
    encoded = base64.b64encode(processed.data).decode("ascii")
    return f"data:{processed.content_type};base64,{encoded}"


def _is_timeout_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {
        "APITimeoutError",
        "ConnectTimeout",
        "PoolTimeout",
        "ReadTimeout",
        "TimeoutException",
    }


def _elapsed_ms(start_time: float) -> int:
    return max(0, round((time.perf_counter() - start_time) * 1000))


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        return default

    return max(minimum, min(value, maximum))


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError:
        return default

    return max(minimum, min(value, maximum))


def _env_image_detail(name: str, default: str) -> str:
    raw_value = os.getenv(name, default).strip().casefold()

    if raw_value not in SUPPORTED_IMAGE_DETAILS:
        return default

    return raw_value


def _target_long_edges(image: Image.Image, max_long_edge: int) -> list[int]:
    original_long_edge = max(image.width, image.height)
    first_edge = min(max_long_edge, original_long_edge)
    edges = [first_edge]

    for fallback_edge in (1440, 1280, 1120):
        if fallback_edge < first_edge:
            edges.append(fallback_edge)

    return edges


def _jpeg_quality_steps(jpeg_quality: int, min_jpeg_quality: int) -> list[int]:
    top_quality = max(min(jpeg_quality, 95), min_jpeg_quality)
    floor_quality = max(min(min_jpeg_quality, top_quality), 1)

    if top_quality == floor_quality:
        return [top_quality]

    return [top_quality, floor_quality]


def _resize_to_long_edge(image: Image.Image, max_long_edge: int) -> Image.Image:
    long_edge = max(image.width, image.height)

    if long_edge <= max_long_edge:
        return image.copy()

    scale = max_long_edge / long_edge
    new_size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()
