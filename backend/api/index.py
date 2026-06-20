import logging
import os
import time
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.comparison import verify_label
from app.models import ApplicationData, VerificationResult
from app.vision import (
    OpenAIVisionService,
    VisionConfigurationError,
    VisionInputError,
    VisionParseError,
    VisionProviderError,
    VisionService,
    VisionTimeoutError,
)


SERVICE_NAME = "ttb-label-verification"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024
LATENCY_BUDGET_MS = 5000
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
APPLICATION_FIELDS = (
    "brand_name",
    "product_class",
    "producer_name",
    "country_of_origin",
    "alcohol_by_volume",
    "net_contents",
    "government_warning",
)

logger = logging.getLogger(__name__)


def allowed_origins() -> list[str]:
    raw_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


app = FastAPI(title="TTB Label Verification API")

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
    return OpenAIVisionService.from_env()


@app.post("/verify", response_model=VerificationResult)
async def verify(
    image: UploadFile | None = File(default=None),
    brand_name: str | None = Form(default=None),
    product_class: str | None = Form(default=None),
    producer_name: str | None = Form(default=None),
    country_of_origin: str | None = Form(default=None),
    alcohol_by_volume: str | None = Form(default=None),
    net_contents: str | None = Form(default=None),
    government_warning: str | None = Form(default=None),
    vision_service: VisionService = Depends(get_vision_service),
) -> VerificationResult | JSONResponse:
    start_time = time.perf_counter()

    try:
        form_values = _validate_application_fields(
            {
                "brand_name": brand_name,
                "product_class": product_class,
                "producer_name": producer_name,
                "country_of_origin": country_of_origin,
                "alcohol_by_volume": alcohol_by_volume,
                "net_contents": net_contents,
                "government_warning": government_warning,
            },
            start_time,
        )
        image_bytes = await _validate_and_read_image(image, start_time)

        application = ApplicationData(**form_values)
        extracted = vision_service.extract(image_bytes, image.content_type)
        result = verify_label(application, extracted)
        result.latency_ms = _elapsed_ms(start_time)

        failed_fields = sum(field.status == "FAIL" for field in result.fields)
        _log_completion(
            result.verdict,
            result.latency_ms,
            image.content_type,
            len(image_bytes),
            failed_fields,
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


def _validate_application_fields(
    values: dict[str, str | None],
    start_time: float,
) -> dict[str, str]:
    cleaned: dict[str, str] = {}

    for field in APPLICATION_FIELDS:
        value = values[field]

        if value is None:
            raise _http_error(
                422,
                "missing_required_field",
                f"{field} is required.",
                start_time,
            )

        cleaned_value = value.strip()

        if cleaned_value == "":
            raise _http_error(
                422,
                "missing_required_field",
                f"{field} cannot be blank.",
                start_time,
            )

        cleaned[field] = cleaned_value

    return cleaned


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


def _elapsed_ms(start_time: float) -> int:
    return max(0, round((time.perf_counter() - start_time) * 1000))


def _log_completion(
    verdict: str,
    latency_ms: int,
    content_type: str | None,
    byte_size: int,
    failed_fields: int,
) -> None:
    log_message = (
        "verify completed verdict=%s latency_ms=%s content_type=%s bytes=%s failed_fields=%s"
    )
    log_args = (verdict, latency_ms, content_type, byte_size, failed_fields)

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
