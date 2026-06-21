import argparse
import json
import statistics
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont


WARNING = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH "
    "DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO "
    "DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)

VALID_FORM = {
    "brand_name": "Acme Cellars",
    "product_class": "Red Wine",
    "producer_name": "Acme Winery LLC",
    "country_of_origin": "United States",
    "alcohol_by_volume": "13.5%",
    "net_contents": "750 mL",
    "government_warning": WARNING,
}


class CheckFailure(AssertionError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase 6 checklist against a deployed TTB backend URL."
    )
    parser.add_argument(
        "base_url",
        help="Backend base URL, for example https://example.vercel.app",
    )
    parser.add_argument(
        "--speed-runs",
        type=int,
        default=5,
        help="Number of valid single-label requests for latency measurement.",
    )
    parser.add_argument(
        "--latency-budget-ms",
        type=int,
        default=5000,
        help="Maximum allowed single-label server latency.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=45.0) as client:
        try:
            run_checklist(
                client,
                base_url,
                max(1, args.speed_runs),
                args.latency_budget_ms,
                results,
            )
        except CheckFailure as exc:
            print(json.dumps({"status": "failed", "failure": str(exc), "results": results}, indent=2))
            return 1

    print(json.dumps({"status": "passed", "results": results}, indent=2))
    return 0


def run_checklist(
    client: httpx.Client,
    base_url: str,
    speed_runs: int,
    latency_budget_ms: int,
    results: list[dict[str, Any]],
) -> None:
    valid_image = label_image()
    wrong_caps_warning_image = label_image(warning=WARNING.title())
    missing_warning_image = label_image(warning=None)
    imperfect_image = label_image().filter(ImageFilter.GaussianBlur(radius=4))
    corrupt_image = b"not an image"

    valid_payload = post_verify(client, base_url, VALID_FORM, image_bytes(valid_image), "valid_label")
    results.append(valid_payload)
    require(valid_payload["status_code"] == 200, "valid label did not return 200")
    require(valid_payload["payload"]["verdict"] == "PASS", "valid label did not pass")
    require(
        valid_payload["payload"]["latency_ms"] < latency_budget_ms,
        "valid label server latency was not under 5 seconds",
    )

    mismatch_form = {**VALID_FORM, "brand_name": "Different Cellars"}
    mismatch_payload = post_verify(
        client,
        base_url,
        mismatch_form,
        image_bytes(valid_image),
        "mismatched_brand",
    )
    results.append(mismatch_payload)
    require(mismatch_payload["status_code"] == 200, "mismatch did not return 200")
    require(
        mismatch_payload["payload"]["verdict"] == "NEEDS_REVIEW",
        "mismatch did not return NEEDS_REVIEW",
    )
    require(field_status(mismatch_payload["payload"], "brand_name") == "FAIL", "brand mismatch did not fail")

    case_only_form = {**VALID_FORM, "brand_name": "ACME CELLARS"}
    case_only_payload = post_verify(
        client,
        base_url,
        case_only_form,
        image_bytes(valid_image),
        "case_only_brand",
    )
    results.append(case_only_payload)
    require(case_only_payload["status_code"] == 200, "case-only check did not return 200")
    require(case_only_payload["payload"]["verdict"] == "PASS", "case-only brand did not pass")

    require(field_status(valid_payload["payload"], "alcohol_by_volume") == "PASS", "ABV normalization failed")
    require(field_status(valid_payload["payload"], "net_contents") == "PASS", "unit normalization failed")
    require(field_status(valid_payload["payload"], "government_warning") == "PASS", "correct warning failed")

    missing_warning_payload = post_verify(
        client,
        base_url,
        VALID_FORM,
        image_bytes(missing_warning_image),
        "missing_warning",
    )
    results.append(missing_warning_payload)
    require(missing_warning_payload["status_code"] == 200, "missing warning did not return 200")
    require(
        field_status(missing_warning_payload["payload"], "government_warning") == "FAIL",
        "missing warning did not fail",
    )

    wrong_caps_payload = post_verify(
        client,
        base_url,
        VALID_FORM,
        image_bytes(wrong_caps_warning_image),
        "wrong_caps_warning",
    )
    results.append(wrong_caps_payload)
    require(wrong_caps_payload["status_code"] == 200, "wrong-caps warning did not return 200")
    require(
        field_status(wrong_caps_payload["payload"], "government_warning") == "FAIL",
        "wrong-caps warning did not fail",
    )

    imperfect_payload = post_verify(
        client,
        base_url,
        VALID_FORM,
        image_bytes(imperfect_image),
        "imperfect_image",
    )
    results.append(imperfect_payload)
    require(
        imperfect_payload["status_code"] in {200, 400, 502, 504},
        "imperfect image returned an unexpected status",
    )
    if imperfect_payload["status_code"] == 200:
        require(
            imperfect_payload["payload"]["verdict"] in {"PASS", "NEEDS_REVIEW"},
            "imperfect image returned an unexpected verdict",
        )
        require(
            isinstance(imperfect_payload["payload"].get("fields"), list),
            "imperfect image success response was not shaped",
        )
    else:
        require("error" in imperfect_payload["payload"], "imperfect image error was not shaped")

    wrong_type_payload = post_verify(
        client,
        base_url,
        VALID_FORM,
        b"not an image",
        "wrong_file_type",
        content_type="text/plain",
    )
    results.append(wrong_type_payload)
    require(wrong_type_payload["status_code"] == 415, "wrong file type did not return 415")
    require(
        wrong_type_payload["payload"]["error"]["code"] == "unsupported_image_type",
        "wrong file type returned the wrong error code",
    )

    empty_submit_payload = timed_request(
        "empty_submit",
        lambda: client.post(f"{base_url}/verify", data={}),
    )
    results.append(empty_submit_payload)
    require(empty_submit_payload["status_code"] == 422, "empty submit did not return 422")
    require("error" in empty_submit_payload["payload"], "empty submit error was not shaped")

    batch_payload = post_batch(
        client,
        base_url,
        VALID_FORM,
        [
            ("valid.jpg", image_bytes(valid_image), "image/jpeg"),
            ("wrong-caps.jpg", image_bytes(wrong_caps_warning_image), "image/jpeg"),
            ("corrupt.jpg", corrupt_image, "image/jpeg"),
        ],
        "batch_summary",
    )
    results.append(batch_payload)
    require(batch_payload["status_code"] == 200, "batch summary did not return 200")
    require(
        batch_payload["payload"]["summary"] == {
            "total": 3,
            "passed": 1,
            "needs_review": 1,
            "errors": 1,
        },
        "batch summary counts were not correct",
    )

    speed_results = [
        post_verify(
            client,
            base_url,
            VALID_FORM,
            image_bytes(valid_image),
            f"single_label_speed_{index + 1}",
        )
        for index in range(speed_runs)
    ]
    server_latencies = [item["payload"]["latency_ms"] for item in speed_results]
    wall_latencies = [item["wall_ms"] for item in speed_results]
    require(all(item["status_code"] == 200 for item in speed_results), "a speed run failed")
    require(all(item["payload"]["verdict"] == "PASS" for item in speed_results), "a speed run did not pass")
    require(
        max(server_latencies) < latency_budget_ms,
        f"single-label max server latency was {max(server_latencies)} ms",
    )
    results.append(
        {
            "check": "single_label_speed_summary",
            "runs": speed_runs,
            "server_latency_ms": summarize(server_latencies),
            "wall_latency_ms": summarize(wall_latencies),
        }
    )


def post_verify(
    client: httpx.Client,
    base_url: str,
    form: dict[str, str],
    content: bytes,
    check: str,
    *,
    content_type: str = "image/jpeg",
) -> dict[str, Any]:
    return timed_request(
        check,
        lambda: client.post(
            f"{base_url}/verify",
            data=form,
            files={"image": ("label.jpg", content, content_type)},
        ),
    )


def post_batch(
    client: httpx.Client,
    base_url: str,
    form: dict[str, str],
    images: list[tuple[str, bytes, str]],
    check: str,
) -> dict[str, Any]:
    return timed_request(
        check,
        lambda: client.post(
            f"{base_url}/verify/batch",
            data=form,
            files=[("images", image) for image in images],
        ),
    )


def timed_request(check: str, send_request) -> dict[str, Any]:
    start = time.perf_counter()
    response = send_request()
    wall_ms = round((time.perf_counter() - start) * 1000)

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text[:500]}

    return {
        "check": check,
        "status_code": response.status_code,
        "wall_ms": wall_ms,
        "payload": payload,
    }


def label_image(warning: str | None = WARNING) -> Image.Image:
    image = Image.new("RGB", (1900, 900), color=(250, 248, 239))
    draw = ImageDraw.Draw(image)
    font = load_font(42)
    small_font = load_font(22)
    warning_font = load_font(18)

    draw.rectangle((55, 55, 1845, 845), outline=(20, 24, 33), width=4)
    draw.text((95, 95), "Acme Cellars", fill=(16, 24, 39), font=font)
    draw.text((95, 175), "Red Wine", fill=(16, 24, 39), font=small_font)
    draw.text((95, 225), "Produced by Acme Winery LLC", fill=(16, 24, 39), font=small_font)
    draw.text((95, 275), "Product of United States", fill=(16, 24, 39), font=small_font)
    draw.text((95, 325), "13.5% Alc./Vol.", fill=(16, 24, 39), font=small_font)
    draw.text((95, 375), "750ml", fill=(16, 24, 39), font=small_font)

    if warning is not None:
        draw_wrapped_text(draw, warning, (95, 680), 1710, warning_font)

    return image


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    origin: tuple[int, int],
    max_width: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x, y = origin
    words = text.split()
    lines: list[str] = []
    current_line = ""

    for word in words:
        candidate = f"{current_line} {word}".strip()

        if current_line and draw.textlength(candidate, font=font) > max_width:
            lines.append(current_line)
            current_line = word
        else:
            current_line = candidate

    if current_line:
        lines.append(current_line)

    for line in lines:
        draw.text((x, y), line, fill=(16, 24, 39), font=font)
        y += 28


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    for font_path in font_candidates:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)

    return ImageFont.load_default()


def image_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


def field_status(payload: dict[str, Any], field_name: str) -> str:
    for field in payload["fields"]:
        if field["field"] == field_name:
            return field["status"]

    raise CheckFailure(f"field {field_name} was not present")


def summarize(values: list[int]) -> dict[str, float | int]:
    sorted_values = sorted(values)
    p95_index = min(len(sorted_values) - 1, max(0, round((len(sorted_values) * 0.95) - 1)))

    return {
        "min": min(values),
        "p50": statistics.median(values),
        "p95": sorted_values[p95_index],
        "max": max(values),
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


if __name__ == "__main__":
    sys.exit(main())
