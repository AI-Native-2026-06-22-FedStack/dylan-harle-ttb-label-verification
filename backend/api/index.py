import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from app.comparison import verify_label
from app.models import (
    ApplicationData,
    BatchError,
    BatchItemResult,
    BatchSummary,
    BatchVerificationResult,
    VerificationResult,
)
from app.vision import (
    VisionConfigurationError,
    VisionInputError,
    VisionParseError,
    VisionProviderError,
    VisionService,
    VisionTimeoutError,
    get_openai_vision_service_from_env,
)


SERVICE_NAME = "ttb-label-verification"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_BATCH_IMAGES = 10
BATCH_CONCURRENCY_DEFAULT = 3
UPLOAD_CHUNK_BYTES = 64 * 1024
LATENCY_BUDGET_MS = 5000
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
APPLICATION_FIELDS = (
    "brand_name",
    "class_type",
    "producer",
    "country_of_origin",
    "abv",
    "net_contents",
    "government_warning",
)
FIELD_LABELS = {
    "brand_name": "Brand Name",
    "class_type": "Product Type",
    "producer": "Producer Name",
    "country_of_origin": "Country of Origin",
    "abv": "Alcohol by Volume",
    "net_contents": "Net Contents",
    "government_warning": "Government Warning",
}
FIELD_MAX_LENGTHS = {
    "brand_name": 160,
    "class_type": 160,
    "producer": 200,
    "country_of_origin": 120,
    "abv": 80,
    "net_contents": 80,
    "government_warning": 650,
}

logger = logging.getLogger(__name__)
load_dotenv()


def allowed_origins() -> list[str]:
    raw_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def configured_vision_model() -> str:
    return os.getenv("OPENAI_VISION_MODEL", "").strip()


def log_startup_configuration() -> None:
    model = configured_vision_model() or "<missing>"
    logger.info(
        "startup configuration app_env=%s allowed_origins=%s vision_model=%s",
        os.getenv("APP_ENV", "local"),
        ",".join(allowed_origins()),
        model,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log_startup_configuration()
    yield


app = FastAPI(title="TTB Label Verification API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "environment": os.getenv("APP_ENV", "local"),
    }


def get_vision_service() -> VisionService:
    return get_openai_vision_service_from_env()


@app.post("/verify", response_model=VerificationResult)
async def verify(
    image: UploadFile | None = File(default=None),
    brand_name: str | None = Form(default=None),
    class_type: str | None = Form(default=None),
    producer: str | None = Form(default=None),
    country_of_origin: str | None = Form(default=None),
    abv: str | None = Form(default=None),
    net_contents: str | None = Form(default=None),
    government_warning: str | None = Form(default=None),
    vision_service: VisionService = Depends(get_vision_service),
) -> VerificationResult | JSONResponse:
    start_time = time.perf_counter()
    timings: dict[str, int] = {}

    try:
        phase_start = time.perf_counter()
        form_values = _validate_application_fields(
            {
                "brand_name": brand_name,
                "class_type": class_type,
                "producer": producer,
                "country_of_origin": country_of_origin,
                "abv": abv,
                "net_contents": net_contents,
                "government_warning": government_warning,
            },
            start_time,
        )
        timings["validation_ms"] = _elapsed_ms(phase_start)
        phase_start = time.perf_counter()
        image_bytes = await _validate_and_read_image(image, start_time)
        timings["image_read_ms"] = _elapsed_ms(phase_start)

        application = ApplicationData(**form_values)
        phase_start = time.perf_counter()
        extracted = await asyncio.to_thread(vision_service.extract, image_bytes, image.content_type)
        timings["extraction_ms"] = _elapsed_ms(phase_start)
        phase_start = time.perf_counter()
        result = verify_label(application, extracted)
        timings["comparison_ms"] = _elapsed_ms(phase_start)
        result.latency_ms = _elapsed_ms(start_time)

        failed_fields = sum(field.status == "FAIL" for field in result.results)
        _log_completion(
            result.overall_verdict,
            result.latency_ms,
            image.content_type,
            len(image_bytes),
            failed_fields,
            timings,
        )

        return result
    except HTTPException as exc:
        return _error_response(
            exc.status_code,
            str(exc.detail["code"]),
            str(exc.detail["message"]),
            start_time,
        )
    except VisionInputError:
        return _error_response(
            400,
            "invalid_image",
            "We could not read that image. Please upload a clear JPEG, PNG, or WebP label photo.",
            start_time,
        )
    except VisionConfigurationError:
        return _error_response(
            503,
            "vision_not_configured",
            "Label extraction is not configured right now. Please try again later.",
            start_time,
        )
    except VisionTimeoutError:
        return _error_response(
            504,
            "vision_timeout",
            "Label extraction took too long. Please try a clearer or smaller image.",
            start_time,
        )
    except VisionParseError:
        return _error_response(
            502,
            "extraction_unavailable",
            "Label extraction returned an unreadable result. Please try again.",
            start_time,
        )
    except VisionProviderError:
        return _error_response(
            502,
            "extraction_unavailable",
            "Label extraction is temporarily unavailable. Please try again.",
            start_time,
        )
    except Exception:
        logger.exception("Unexpected verification failure")
        return _error_response(
            500,
            "verification_failed",
            "Verification failed unexpectedly. Please try again.",
            start_time,
        )


@app.post("/verify/batch", response_model=BatchVerificationResult)
async def verify_batch(
    images: list[UploadFile] | None = File(default=None),
    applications: str | None = Form(default=None),
    vision_service: VisionService = Depends(get_vision_service),
) -> BatchVerificationResult | JSONResponse:
    start_time = time.perf_counter()
    timings: dict[str, int] = {}

    try:
        phase_start = time.perf_counter()
        upload_items = await _validate_and_read_batch_images(images, start_time)
        timings["image_read_ms"] = _elapsed_ms(phase_start)
        phase_start = time.perf_counter()
        application_items = _validate_batch_applications(applications, len(upload_items), start_time)
        timings["validation_ms"] = _elapsed_ms(phase_start)
        concurrency = _batch_concurrency()
        semaphore = asyncio.Semaphore(concurrency)

        items = await asyncio.gather(
            *(
                _verify_batch_item(
                    item["index"],
                    item["filename"],
                    item["content"],
                    item["content_type"],
                    application_items[item["index"]],
                    vision_service,
                    semaphore,
                )
                for item in upload_items
            )
        )
        summary = _batch_summary(items)
        latency_ms = _elapsed_ms(start_time)
        _log_batch_completion(summary, latency_ms, concurrency, timings)

        return BatchVerificationResult(
            summary=summary,
            items=items,
            latency_ms=latency_ms,
        )
    except HTTPException as exc:
        return _error_response(
            exc.status_code,
            str(exc.detail["code"]),
            str(exc.detail["message"]),
            start_time,
        )
    except Exception:
        logger.exception("Unexpected batch verification failure")
        return _error_response(
            500,
            "batch_verification_failed",
            "Batch verification failed unexpectedly. Please try again.",
            start_time,
        )


def _validate_application_fields(
    values: dict[str, str | None],
    start_time: float,
) -> dict[str, str]:
    cleaned: dict[str, str] = {}

    for field in APPLICATION_FIELDS:
        value = values[field]
        label = FIELD_LABELS[field]

        if value is None:
            raise _http_error(
                422,
                "missing_required_field",
                f"Please enter {label}.",
                start_time,
            )

        if not isinstance(value, str):
            raise _http_error(
                422,
                "invalid_field_value",
                f"{label} must be text.",
                start_time,
            )

        cleaned_value = value.strip()

        if cleaned_value == "":
            raise _http_error(
                422,
                "missing_required_field",
                f"Please enter {label}.",
                start_time,
            )

        max_length = FIELD_MAX_LENGTHS[field]

        if len(cleaned_value) > max_length:
            raise _http_error(
                422,
                "invalid_field_value",
                f"{label} is too long. Please use {max_length} characters or fewer.",
                start_time,
            )

        cleaned[field] = cleaned_value

    return cleaned


def _validate_batch_applications(
    applications: str | None,
    image_count: int,
    start_time: float,
) -> list[ApplicationData]:
    if applications is None:
        raise _http_error(
            422,
            "missing_required_field",
            "Please provide application data for each label image.",
            start_time,
        )

    try:
        parsed = json.loads(applications)
    except json.JSONDecodeError:
        raise _http_error(
            422,
            "invalid_field_value",
            "Batch application data must be valid JSON.",
            start_time,
        ) from None

    if not isinstance(parsed, list):
        raise _http_error(
            422,
            "invalid_field_value",
            "Batch application data must be a JSON array.",
            start_time,
        )

    if len(parsed) != image_count:
        raise _http_error(
            422,
            "invalid_field_value",
            "Please provide one application record for each label image.",
            start_time,
        )

    application_items: list[ApplicationData] = []

    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise _http_error(
                422,
                "invalid_field_value",
                f"Application record {index + 1} must be an object.",
                start_time,
            )

        cleaned = _validate_application_fields(
            {field: item.get(field) for field in APPLICATION_FIELDS},
            start_time,
        )
        application_items.append(ApplicationData(**cleaned))

    return application_items


async def _validate_and_read_batch_images(
    images: list[UploadFile] | None,
    start_time: float,
) -> list[dict[str, Any]]:
    if not images:
        raise _http_error(
            422,
            "missing_required_field",
            "Please upload at least one label image.",
            start_time,
        )

    if len(images) > MAX_BATCH_IMAGES:
        raise _http_error(
            422,
            "too_many_images",
            "Please upload 10 or fewer label images.",
            start_time,
        )

    upload_items: list[dict[str, Any]] = []

    for index, image in enumerate(images):
        image_bytes = await _validate_and_read_image(image, start_time)
        upload_items.append(
            {
                "index": index,
                "filename": image.filename or f"Label {index + 1}",
                "content_type": image.content_type,
                "content": image_bytes,
            }
        )

    return upload_items


async def _validate_and_read_image(
    image: UploadFile | None,
    start_time: float,
) -> bytes:
    if image is None:
        raise _http_error(
            422,
            "missing_required_field",
            "Please upload a label image.",
            start_time,
        )

    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        raise _http_error(
            415,
            "unsupported_image_type",
            "Please upload a JPEG, PNG, or WebP image.",
            start_time,
        )

    image_bytes = bytearray()

    while True:
        chunk = await image.read(UPLOAD_CHUNK_BYTES)

        if not chunk:
            break

        image_bytes.extend(chunk)

        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise _http_error(
                413,
                "image_too_large",
                "Please upload an image under 2 MB.",
                start_time,
            )

    if len(image_bytes) == 0:
        raise _http_error(
            422,
            "empty_upload",
            "The uploaded image is empty. Please choose a label photo.",
            start_time,
        )

    return bytes(image_bytes)


def _http_error(
    status_code: int,
    code: str,
    message: str,
    start_time: float,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "latency_ms": _elapsed_ms(start_time),
        },
    )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    start_time: float,
) -> JSONResponse:
    latency_ms = _elapsed_ms(start_time)
    _log_error(status_code, code, latency_ms)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "latency_ms": latency_ms,
            }
        },
    )


async def _verify_batch_item(
    index: int,
    filename: str,
    image_bytes: bytes,
    content_type: str | None,
    application: ApplicationData,
    vision_service: VisionService,
    semaphore: asyncio.Semaphore,
) -> BatchItemResult:
    item_start = time.perf_counter()

    async with semaphore:
        try:
            phase_start = time.perf_counter()
            extracted = await asyncio.to_thread(
                vision_service.extract,
                image_bytes,
                content_type,
            )
            extraction_ms = _elapsed_ms(phase_start)
            phase_start = time.perf_counter()
            result = verify_label(application, extracted)
            comparison_ms = _elapsed_ms(phase_start)
            item_latency_ms = _elapsed_ms(item_start)
            result.latency_ms = item_latency_ms
            logger.info(
                "verify batch item completed index=%s status=%s latency_ms=%s "
                "extraction_ms=%s comparison_ms=%s content_type=%s bytes=%s",
                index,
                result.overall_verdict,
                item_latency_ms,
                extraction_ms,
                comparison_ms,
                content_type,
                len(image_bytes),
            )

            return BatchItemResult(
                index=index,
                filename=filename,
                status=result.overall_verdict,
                result=result,
                latency_ms=item_latency_ms,
            )
        except VisionInputError:
            return _batch_item_error(
                index,
                filename,
                "invalid_image",
                "We could not read this image. Please use a clear JPEG, PNG, or WebP label photo.",
                item_start,
            )
        except VisionConfigurationError:
            return _batch_item_error(
                index,
                filename,
                "vision_not_configured",
                "Label extraction is not configured right now. Please try again later.",
                item_start,
            )
        except VisionTimeoutError:
            return _batch_item_error(
                index,
                filename,
                "vision_timeout",
                "Label extraction took too long for this image.",
                item_start,
            )
        except (VisionParseError, VisionProviderError):
            return _batch_item_error(
                index,
                filename,
                "extraction_unavailable",
                "Label extraction failed for this image. Please try again.",
                item_start,
            )
        except Exception:
            logger.exception("Unexpected batch item failure")
            return _batch_item_error(
                index,
                filename,
                "verification_failed",
                "Verification failed for this image. Please try again.",
                item_start,
            )


def _batch_item_error(
    index: int,
    filename: str,
    code: str,
    message: str,
    start_time: float,
) -> BatchItemResult:
    return BatchItemResult(
        index=index,
        filename=filename,
        status="ERROR",
        error=BatchError(code=code, message=message),
        latency_ms=_elapsed_ms(start_time),
    )


def _batch_summary(items: list[BatchItemResult]) -> BatchSummary:
    passed = sum(item.status == "APPROVED" for item in items)
    needs_review = sum(item.status in {"NEEDS_REVIEW", "ERROR"} for item in items)

    return BatchSummary(
        total=len(items),
        passed=passed,
        needs_review=needs_review,
    )


def _batch_concurrency() -> int:
    raw_value = os.getenv("BATCH_CONCURRENCY", str(BATCH_CONCURRENCY_DEFAULT))

    try:
        value = int(raw_value)
    except ValueError:
        return BATCH_CONCURRENCY_DEFAULT

    return max(1, min(value, MAX_BATCH_IMAGES))


def _elapsed_ms(start_time: float) -> int:
    return max(0, round((time.perf_counter() - start_time) * 1000))


def _log_completion(
    verdict: str,
    latency_ms: int,
    content_type: str | None,
    byte_size: int,
    failed_fields: int,
    timings: dict[str, int],
) -> None:
    log_message = (
        "verify completed verdict=%s latency_ms=%s content_type=%s bytes=%s "
        "failed_fields=%s validation_ms=%s image_read_ms=%s extraction_ms=%s "
        "comparison_ms=%s"
    )
    log_args = (
        verdict,
        latency_ms,
        content_type,
        byte_size,
        failed_fields,
        timings.get("validation_ms", 0),
        timings.get("image_read_ms", 0),
        timings.get("extraction_ms", 0),
        timings.get("comparison_ms", 0),
    )

    if latency_ms > LATENCY_BUDGET_MS:
        logger.warning(log_message, *log_args)
    else:
        logger.info(log_message, *log_args)


def _log_error(status_code: int, code: str, latency_ms: int) -> None:
    log_message = "verify failed status=%s code=%s latency_ms=%s"
    log_args = (status_code, code, latency_ms)

    if latency_ms > LATENCY_BUDGET_MS:
        logger.warning(log_message, *log_args)
    elif status_code >= 500:
        logger.error(log_message, *log_args)
    else:
        logger.info(log_message, *log_args)


def _log_batch_completion(
    summary: BatchSummary,
    latency_ms: int,
    concurrency: int,
    timings: dict[str, int],
) -> None:
    log_message = (
        "verify batch completed total=%s passed=%s needs_review=%s "
        "latency_ms=%s concurrency=%s validation_ms=%s image_read_ms=%s"
    )
    log_args = (
        summary.total,
        summary.passed,
        summary.needs_review,
        latency_ms,
        concurrency,
        timings.get("validation_ms", 0),
        timings.get("image_read_ms", 0),
    )

    if latency_ms > LATENCY_BUDGET_MS:
        logger.warning(log_message, *log_args)
    else:
        logger.info(log_message, *log_args)
