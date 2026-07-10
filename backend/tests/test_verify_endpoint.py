import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import api.index as api_index
from api.index import FIELD_LABELS, FIELD_MAX_LENGTHS, MAX_UPLOAD_BYTES, app, get_vision_service
from app.models import ExtractedLabel
from app.vision import (
    FakeVisionService,
    VisionConfigurationError,
    VisionInputError,
    VisionParseError,
    VisionProviderError,
    VisionTimeoutError,
)


WARNING = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH "
    "DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO "
    "DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides.clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def valid_form(**overrides: str) -> dict[str, str]:
    form = {
        "brand_name": "Acme Cellars",
        "class_type": "Red Wine",
        "producer": "Acme Winery LLC",
        "country_of_origin": "United States",
        "abv": "13.5%",
        "net_contents": "750 mL",
        "government_warning": WARNING,
    }
    form.update(overrides)
    return form


def extracted_label(**overrides: str | None) -> ExtractedLabel:
    label = {
        "brand_name": "ACME CELLARS",
        "class_type": "Red Wine",
        "producer": "Acme Winery LLC",
        "country_of_origin": "United States",
        "abv": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "government_warning": WARNING,
    }
    label.update(overrides)
    return ExtractedLabel(**label)


def image_file(
    content: bytes = b"fake image bytes",
    content_type: str = "image/jpeg",
) -> dict[str, tuple[str, bytes, str]]:
    return {"image": ("label.jpg", content, content_type)}


def override_vision_service(fake_service: FakeVisionService) -> None:
    app.dependency_overrides[get_vision_service] = lambda: fake_service


def error_payload(response):
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "latency_ms"}
    assert isinstance(payload["error"]["message"], str)
    assert isinstance(payload["error"]["latency_ms"], int)
    assert "Traceback" not in response.text
    return payload["error"]


def test_verify_success_returns_full_verification_result(client: TestClient):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)

    response = client.post("/verify", data=valid_form(), files=image_file())

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_verdict"] == "APPROVED"
    assert isinstance(payload["latency_ms"], int)
    assert len(payload["results"]) == 7
    assert fake_service.calls == [(b"fake image bytes", "image/jpeg")]

    brand_result = next(field for field in payload["results"] if field["field"] == "brand_name")
    assert brand_result["expected"] == "Acme Cellars"
    assert brand_result["found"] == "ACME CELLARS"


def test_get_vision_service_returns_cached_env_service_directly(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_service = FakeVisionService(result=extracted_label())
    monkeypatch.setattr(api_index, "get_openai_vision_service_from_env", lambda: fake_service)

    assert get_vision_service() is fake_service


def test_startup_configuration_log_includes_public_config_without_secret(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://frontend-gamma-silk-13.vercel.app")
    monkeypatch.setenv("OPENAI_VISION_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    caplog.set_level(logging.INFO, logger="api.index")

    api_index.log_startup_configuration()

    assert "app_env=production" in caplog.text
    assert "allowed_origins=https://frontend-gamma-silk-13.vercel.app" in caplog.text
    assert "vision_model=gpt-5.4-mini" in caplog.text
    assert "sk-test-secret-value" not in caplog.text


def test_verify_logs_warning_when_latency_exceeds_budget(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)
    monkeypatch.setattr(api_index, "_elapsed_ms", lambda start_time: 5100)
    caplog.set_level(logging.WARNING, logger="api.index")

    response = client.post("/verify", data=valid_form(), files=image_file())

    assert response.status_code == 200
    assert response.json()["latency_ms"] == 5100
    assert "verify completed verdict=APPROVED latency_ms=5100" in caplog.text
    assert "validation_ms=" in caplog.text
    assert "extraction_ms=" in caplog.text


def test_verify_needs_review_returns_expected_and_extracted_values(client: TestClient):
    fake_service = FakeVisionService(result=extracted_label(brand_name="Different Brand"))
    override_vision_service(fake_service)

    response = client.post("/verify", data=valid_form(), files=image_file())

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_verdict"] == "NEEDS_REVIEW"

    brand_result = next(field for field in payload["results"] if field["field"] == "brand_name")
    assert brand_result["status"] == "FAIL"
    assert brand_result["expected"] == "Acme Cellars"
    assert brand_result["found"] == "Different Brand"


def test_verify_warning_mismatch_surfaces_extracted_warning_text(client: TestClient):
    misread_warning = WARNING.replace("SURGEON", "SUREEON")
    fake_service = FakeVisionService(result=extracted_label(government_warning=misread_warning))
    override_vision_service(fake_service)

    response = client.post("/verify", data=valid_form(), files=image_file())

    assert response.status_code == 200
    warning_result = next(
        field for field in response.json()["results"] if field["field"] == "government_warning"
    )
    assert warning_result["status"] == "FAIL"
    assert warning_result["expected"] == WARNING
    assert warning_result["found"] == misread_warning


def test_verify_missing_image_returns_shaped_422_without_calling_service(client: TestClient):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)

    response = client.post("/verify", data=valid_form())

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "missing_required_field"
    assert "image" in error["message"].casefold()
    assert fake_service.calls == []


def test_verify_empty_image_returns_shaped_422_without_calling_service(client: TestClient):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)

    response = client.post("/verify", data=valid_form(), files=image_file(content=b""))

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "empty_upload"
    assert "empty" in error["message"].casefold()
    assert fake_service.calls == []


@pytest.mark.parametrize("field", list(valid_form().keys()))
def test_verify_missing_field_returns_shaped_422_without_calling_service(
    client: TestClient,
    field: str,
):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)
    form = valid_form()
    del form[field]

    response = client.post("/verify", data=form, files=image_file())

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "missing_required_field"
    assert error["message"] == f"Please enter {FIELD_LABELS[field]}."
    assert "_" not in error["message"]
    assert fake_service.calls == []


@pytest.mark.parametrize("field", list(valid_form().keys()))
def test_verify_blank_field_returns_shaped_422_without_calling_service(
    client: TestClient,
    field: str,
):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)

    response = client.post("/verify", data=valid_form(**{field: "   "}), files=image_file())

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "missing_required_field"
    assert error["message"] == f"Please enter {FIELD_LABELS[field]}."
    assert "_" not in error["message"]
    assert fake_service.calls == []


@pytest.mark.parametrize("field", list(valid_form().keys()))
def test_verify_too_long_field_returns_friendly_422_without_calling_service(
    client: TestClient,
    field: str,
):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)
    too_long_value = "x" * (FIELD_MAX_LENGTHS[field] + 1)

    response = client.post("/verify", data=valid_form(**{field: too_long_value}), files=image_file())

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "invalid_field_value"
    assert error["message"] == (
        f"{FIELD_LABELS[field]} is too long. "
        f"Please use {FIELD_MAX_LENGTHS[field]} characters or fewer."
    )
    assert "_" not in error["message"]
    assert fake_service.calls == []


def test_verify_unsupported_content_type_returns_shaped_415_without_calling_service(
    client: TestClient,
):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)

    response = client.post(
        "/verify",
        data=valid_form(),
        files=image_file(content=b"not an image", content_type="text/plain"),
    )

    assert response.status_code == 415
    error = error_payload(response)
    assert error["code"] == "unsupported_image_type"
    assert "jpeg" in error["message"].casefold()
    assert fake_service.calls == []


def test_verify_oversized_image_returns_shaped_413_without_calling_service(
    client: TestClient,
):
    fake_service = FakeVisionService(result=extracted_label())
    override_vision_service(fake_service)

    response = client.post(
        "/verify",
        data=valid_form(),
        files=image_file(content=b"x" * (MAX_UPLOAD_BYTES + 1)),
    )

    assert response.status_code == 413
    error = error_payload(response)
    assert error["code"] == "image_too_large"
    assert "2 mb" in error["message"].casefold()
    assert fake_service.calls == []


@pytest.mark.parametrize(
    ("service_error", "status_code", "code"),
    [
        (VisionInputError("bad image"), 400, "invalid_image"),
        (VisionConfigurationError("missing key"), 503, "vision_not_configured"),
        (VisionTimeoutError("slow"), 504, "vision_timeout"),
        (VisionParseError("bad parse"), 502, "extraction_unavailable"),
        (VisionProviderError("provider down"), 502, "extraction_unavailable"),
    ],
)
def test_verify_vision_errors_return_shaped_responses(
    client: TestClient,
    service_error: Exception,
    status_code: int,
    code: str,
):
    fake_service = FakeVisionService(error=service_error)
    override_vision_service(fake_service)

    response = client.post("/verify", data=valid_form(), files=image_file())

    assert response.status_code == status_code
    error = error_payload(response)
    assert error["code"] == code
    assert fake_service.calls == [(b"fake image bytes", "image/jpeg")]
