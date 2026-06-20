from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from app.models import ExtractedLabel
from app.vision import (
    DEFAULT_IMAGE_DETAIL,
    FakeVisionService,
    OpenAIVisionService,
    VisionInputError,
    VisionParseError,
    VisionProviderError,
    VisionTimeoutError,
    preprocess_label_image,
)


WARNING = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH "
    "DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO "
    "DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)


class FakeResponses:
    def __init__(self, parsed=None, error: Exception | None = None) -> None:
        self.parsed = parsed
        self.error = error
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)

        if self.error is not None:
            raise self.error

        return SimpleNamespace(output_parsed=self.parsed)


class FakeOpenAIClient:
    def __init__(self, parsed=None, error: Exception | None = None) -> None:
        self.responses = FakeResponses(parsed=parsed, error=error)


def image_bytes(size=(640, 480), image_format="PNG") -> bytes:
    image = Image.new("RGB", size, color=(244, 241, 232))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def populated_payload(**overrides):
    payload = {
        "brand_name": "Acme Cellars",
        "product_class": "Red Wine",
        "producer_name": "Acme Winery LLC",
        "country_of_origin": "United States",
        "alcohol_by_volume": "13.5%",
        "net_contents": "750 mL",
        "government_warning": WARNING,
    }
    payload.update(overrides)
    return payload


def test_fake_vision_service_returns_configured_label_and_records_call():
    expected = ExtractedLabel(brand_name="Acme Cellars")
    service = FakeVisionService(result=expected)

    result = service.extract(b"image bytes", "image/jpeg")

    assert result == expected
    assert service.calls == [(b"image bytes", "image/jpeg")]


def test_openai_service_uses_structured_parse_and_maps_populated_label():
    fake_client = FakeOpenAIClient(parsed=populated_payload())
    service = OpenAIVisionService(client=fake_client, model="test-vision-model")

    result = service.extract(image_bytes(), "image/png")

    assert result == ExtractedLabel(**populated_payload())

    call = fake_client.responses.calls[0]
    assert call["model"] == "test-vision-model"
    assert call["text_format"].__name__ == "VisionExtraction"
    assert call["timeout"] == pytest.approx(4.0)

    user_content = call["input"][1]["content"]
    prompt = user_content[0]["text"]
    image_input = user_content[1]
    assert "government_warning" in prompt
    assert "exactly and verbatim" in prompt
    assert image_input["detail"] == DEFAULT_IMAGE_DETAIL
    assert image_input["image_url"].startswith("data:image/jpeg;base64,")


def test_openai_service_returns_partial_data_for_null_fields():
    fake_client = FakeOpenAIClient(
        parsed=populated_payload(
            product_class=None,
            producer_name=None,
            government_warning=None,
        )
    )
    service = OpenAIVisionService(client=fake_client)

    result = service.extract(image_bytes())

    assert result.brand_name == "Acme Cellars"
    assert result.product_class is None
    assert result.producer_name is None
    assert result.government_warning is None


def test_openai_service_wraps_timeout_as_provider_error():
    fake_client = FakeOpenAIClient(error=TimeoutError("timed out"))
    service = OpenAIVisionService(client=fake_client)

    with pytest.raises(VisionProviderError, match="timed out"):
        service.extract(image_bytes())


def test_openai_service_wraps_sdk_timeout_as_timeout_error():
    api_timeout_error = type("APITimeoutError", (Exception,), {})
    fake_client = FakeOpenAIClient(error=api_timeout_error("timed out"))
    service = OpenAIVisionService(client=fake_client)

    with pytest.raises(VisionTimeoutError, match="timed out"):
        service.extract(image_bytes())


def test_openai_service_wraps_malformed_json_parse_error():
    fake_client = FakeOpenAIClient(error=ValueError("malformed json"))
    service = OpenAIVisionService(client=fake_client)

    with pytest.raises(VisionParseError, match="extraction schema"):
        service.extract(image_bytes())


def test_openai_service_wraps_schema_mismatch_after_parse():
    fake_client = FakeOpenAIClient(parsed={"brand_name": "Acme Cellars"})
    service = OpenAIVisionService(client=fake_client)

    with pytest.raises(VisionParseError, match="extraction schema"):
        service.extract(image_bytes())


def test_preprocess_downscales_large_image_and_outputs_rgb_jpeg():
    processed = preprocess_label_image(
        image_bytes(size=(2400, 1200)),
        max_long_edge=800,
    )

    assert processed.content_type == "image/jpeg"
    assert processed.width == 800
    assert processed.height == 400

    with Image.open(BytesIO(processed.data)) as output:
        assert output.format == "JPEG"
        assert output.mode == "RGB"


def test_preprocess_does_not_upscale_small_image():
    processed = preprocess_label_image(
        image_bytes(size=(320, 240)),
        max_long_edge=800,
    )

    assert processed.width == 320
    assert processed.height == 240


def test_preprocess_rejects_invalid_image_bytes():
    with pytest.raises(VisionInputError, match="could not be decoded"):
        preprocess_label_image(b"not an image")
