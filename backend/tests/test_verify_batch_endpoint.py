import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.index import FIELD_LABELS, MAX_BATCH_IMAGES, MAX_UPLOAD_BYTES, app, get_vision_service
from app.models import ExtractedLabel
from app.vision import VisionProviderError


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


class MappingVisionService:
    def __init__(self, responses: dict[bytes, ExtractedLabel | Exception], delay: float = 0) -> None:
        self.responses = responses
        self.delay = delay
        self.calls: list[tuple[bytes, str | None]] = []
        self._lock = threading.Lock()

    def extract(self, image_bytes: bytes, content_type: str | None = None) -> ExtractedLabel:
        if self.delay:
            time.sleep(self.delay)

        with self._lock:
            self.calls.append((image_bytes, content_type))

        response = self.responses[image_bytes]

        if isinstance(response, Exception):
            raise response

        return response


def valid_form(**overrides: str) -> dict[str, str]:
    form = {
        "brand_name": "Acme Cellars",
        "product_class": "Red Wine",
        "producer_name": "Acme Winery LLC",
        "country_of_origin": "United States",
        "alcohol_by_volume": "13.5%",
        "net_contents": "750 mL",
        "government_warning": WARNING,
    }
    form.update(overrides)
    return form


def extracted_label(**overrides: str | None) -> ExtractedLabel:
    label = {
        "brand_name": "ACME CELLARS",
        "product_class": "Red Wine",
        "producer_name": "Acme Winery LLC",
        "country_of_origin": "United States",
        "alcohol_by_volume": "13.5% Alc./Vol.",
        "net_contents": "750 mL",
        "government_warning": WARNING,
    }
    label.update(overrides)
    return ExtractedLabel(**label)


def image_files(*contents: bytes):
    return [
        ("images", (f"label-{index + 1}.jpg", content, "image/jpeg"))
        for index, content in enumerate(contents)
    ]


def override_vision_service(service: MappingVisionService) -> None:
    app.dependency_overrides[get_vision_service] = lambda: service


def error_payload(response):
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "latency_ms"}
    assert "Traceback" not in response.text
    return payload["error"]


def test_verify_batch_success_all_pass(client: TestClient):
    service = MappingVisionService(
        {
            b"one": extracted_label(),
            b"two": extracted_label(),
            b"three": extracted_label(),
        }
    )
    override_vision_service(service)

    response = client.post("/verify/batch", data=valid_form(), files=image_files(b"one", b"two", b"three"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {"total": 3, "passed": 3, "needs_review": 0, "errors": 0}
    assert isinstance(payload["latency_ms"], int)
    assert [item["index"] for item in payload["items"]] == [0, 1, 2]
    assert [item["filename"] for item in payload["items"]] == [
        "label-1.jpg",
        "label-2.jpg",
        "label-3.jpg",
    ]
    assert all(item["status"] == "PASS" for item in payload["items"])
    assert all(item["result"]["verdict"] == "PASS" for item in payload["items"])


def test_verify_batch_mixed_statuses_and_item_error_isolation(client: TestClient):
    service = MappingVisionService(
        {
            b"pass": extracted_label(),
            b"review": extracted_label(brand_name="Different Brand"),
            b"error": VisionProviderError("provider down"),
        }
    )
    override_vision_service(service)

    response = client.post(
        "/verify/batch",
        data=valid_form(),
        files=image_files(b"pass", b"review", b"error"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {"total": 3, "passed": 1, "needs_review": 1, "errors": 1}
    assert [item["status"] for item in payload["items"]] == ["PASS", "NEEDS_REVIEW", "ERROR"]
    assert payload["items"][0]["result"]["verdict"] == "PASS"
    assert payload["items"][1]["result"]["verdict"] == "NEEDS_REVIEW"
    assert payload["items"][2]["result"] is None
    assert payload["items"][2]["error"]["code"] == "extraction_unavailable"


def test_verify_batch_rejects_missing_images(client: TestClient):
    response = client.post("/verify/batch", data=valid_form())

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "missing_required_field"
    assert "image" in error["message"].casefold()


def test_verify_batch_rejects_too_many_images(client: TestClient):
    files = image_files(*[f"image-{index}".encode() for index in range(MAX_BATCH_IMAGES + 1)])

    response = client.post("/verify/batch", data=valid_form(), files=files)

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "too_many_images"
    assert "10 or fewer" in error["message"]


def test_verify_batch_rejects_unsupported_content_type(client: TestClient):
    response = client.post(
        "/verify/batch",
        data=valid_form(),
        files=[("images", ("label.txt", b"not an image", "text/plain"))],
    )

    assert response.status_code == 415
    error = error_payload(response)
    assert error["code"] == "unsupported_image_type"


def test_verify_batch_rejects_oversized_image(client: TestClient):
    response = client.post(
        "/verify/batch",
        data=valid_form(),
        files=image_files(b"x" * (MAX_UPLOAD_BYTES + 1)),
    )

    assert response.status_code == 413
    error = error_payload(response)
    assert error["code"] == "image_too_large"


def test_verify_batch_rejects_blank_shared_field(client: TestClient):
    response = client.post(
        "/verify/batch",
        data=valid_form(brand_name="   "),
        files=image_files(b"one"),
    )

    assert response.status_code == 422
    error = error_payload(response)
    assert error["code"] == "missing_required_field"
    assert error["message"] == f"Please enter {FIELD_LABELS['brand_name']}."


def test_verify_batch_uses_bounded_concurrency(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BATCH_CONCURRENCY", "3")
    service = MappingVisionService(
        {
            b"one": extracted_label(),
            b"two": extracted_label(),
            b"three": extracted_label(),
        },
        delay=0.2,
    )
    override_vision_service(service)
    start_time = time.perf_counter()

    response = client.post("/verify/batch", data=valid_form(), files=image_files(b"one", b"two", b"three"))

    elapsed = time.perf_counter() - start_time
    assert response.status_code == 200
    assert elapsed < 0.5
    assert len(service.calls) == 3
