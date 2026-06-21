import re
from collections.abc import Callable

from rapidfuzz import fuzz

from app.models import ApplicationData, ExtractedLabel, FieldResult, VerificationResult


FUZZY_STRATEGY = "fuzzy_token_set_ratio"
COUNTRY_STRATEGY = "country_synonym_exact"
ABV_STRATEGY = "abv_numeric_tolerance"
NET_CONTENTS_STRATEGY = "net_contents_ml_tolerance"
WARNING_STRATEGY = "exact_case_sensitive_whitespace_folded"


def _is_missing(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _missing_result(field: str, expected: str, extracted: str | None, strategy: str) -> FieldResult:
    return FieldResult(
        field=field,
        status="FAIL",
        expected=expected,
        extracted=extracted,
        strategy=strategy,
        score=None,
        message="Extracted value is missing.",
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _token_set_ratio(expected: str, extracted: str) -> float:
    expected_tokens = set(re.findall(r"[a-z0-9]+", expected.casefold()))
    extracted_tokens = set(re.findall(r"[a-z0-9]+", extracted.casefold()))

    if not expected_tokens and not extracted_tokens:
        return 100.0
    if expected_tokens == extracted_tokens:
        return 100.0

    expected_joined = " ".join(sorted(expected_tokens))
    extracted_joined = " ".join(sorted(extracted_tokens))

    return float(fuzz.token_set_ratio(expected_joined, extracted_joined))


def _compare_fuzzy(
    field: str,
    expected: str,
    extracted: str | None,
    threshold: float,
) -> FieldResult:
    if _is_missing(extracted):
        return _missing_result(field, expected, extracted, FUZZY_STRATEGY)

    score = _token_set_ratio(_normalize_text(expected), _normalize_text(extracted))
    status = "PASS" if score >= threshold else "FAIL"

    return FieldResult(
        field=field,
        status=status,
        expected=expected,
        extracted=extracted,
        strategy=FUZZY_STRATEGY,
        score=round(score, 2),
        message=f"Fuzzy score {score:.2f}; threshold {threshold:.2f}.",
    )


def compare_brand_name(expected: str, extracted: str | None) -> FieldResult:
    return _compare_fuzzy("brand_name", expected, extracted, threshold=90)


def compare_product_class(expected: str, extracted: str | None) -> FieldResult:
    return _compare_fuzzy("product_class", expected, extracted, threshold=88)


def compare_producer_name(expected: str, extracted: str | None) -> FieldResult:
    return _compare_fuzzy("producer_name", expected, extracted, threshold=90)


COUNTRY_SYNONYMS = {
    "theunitedstates": "united states",
    "theunitedstatesofamerica": "united states",
    "us": "united states",
    "usa": "united states",
    "unitedstates": "united states",
    "unitedstatesofamerica": "united states",
    "uk": "united kingdom",
    "u k": "united kingdom",
    "unitedkingdom": "united kingdom",
    "greatbritain": "united kingdom",
}

COUNTRY_PREFIX_TOKENS = (
    ("country", "of", "origin"),
    ("product", "of"),
    ("produced", "in"),
    ("made", "in"),
    ("bottled", "in"),
    ("imported", "from"),
    ("origin",),
)


def _country_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _country_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _strip_country_prefix(tokens: list[str]) -> list[str]:
    for prefix in COUNTRY_PREFIX_TOKENS:
        prefix_length = len(prefix)

        if len(tokens) > prefix_length and tuple(tokens[:prefix_length]) == prefix:
            return tokens[prefix_length:]

    return tokens


def _canonical_country(value: str) -> str:
    tokens = _country_tokens(value)

    while True:
        stripped_tokens = _strip_country_prefix(tokens)

        if stripped_tokens == tokens:
            break

        tokens = stripped_tokens

    key = _country_key(" ".join(tokens))
    return COUNTRY_SYNONYMS.get(key, " ".join(tokens))


def compare_country_of_origin(expected: str, extracted: str | None) -> FieldResult:
    if _is_missing(extracted):
        return _missing_result("country_of_origin", expected, extracted, COUNTRY_STRATEGY)

    expected_country = _canonical_country(expected)
    extracted_country = _canonical_country(extracted)
    status = "PASS" if expected_country == extracted_country else "FAIL"

    return FieldResult(
        field="country_of_origin",
        status=status,
        expected=expected,
        extracted=extracted,
        strategy=COUNTRY_STRATEGY,
        score=100.0 if status == "PASS" else 0.0,
        message=f"Expected canonical country '{expected_country}', got '{extracted_country}'.",
    )


def _parse_percentage(value: str) -> float | None:
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    if percent_match:
        return float(percent_match.group(1))

    number_match = re.search(r"\d+(?:\.\d+)?", value)
    if number_match:
        return float(number_match.group(0))

    return None


def compare_alcohol_by_volume(expected: str, extracted: str | None) -> FieldResult:
    if _is_missing(extracted):
        return _missing_result("alcohol_by_volume", expected, extracted, ABV_STRATEGY)

    expected_value = _parse_percentage(expected)
    extracted_value = _parse_percentage(extracted)

    if expected_value is None or extracted_value is None:
        return FieldResult(
            field="alcohol_by_volume",
            status="FAIL",
            expected=expected,
            extracted=extracted,
            strategy=ABV_STRATEGY,
            score=None,
            message="Could not parse ABV percentage.",
        )

    difference = abs(expected_value - extracted_value)
    status = "PASS" if difference <= 0.1 else "FAIL"

    return FieldResult(
        field="alcohol_by_volume",
        status=status,
        expected=expected,
        extracted=extracted,
        strategy=ABV_STRATEGY,
        score=round(difference, 3),
        message=f"ABV difference is {difference:.3f}; tolerance is 0.100.",
    )


UNIT_TO_ML = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "cl": 10.0,
}


def _parse_net_contents_ml(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)", value)
    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2).casefold()
    multiplier = UNIT_TO_ML.get(unit)

    if multiplier is None:
        return None

    return amount * multiplier


def compare_net_contents(expected: str, extracted: str | None) -> FieldResult:
    if _is_missing(extracted):
        return _missing_result("net_contents", expected, extracted, NET_CONTENTS_STRATEGY)

    expected_ml = _parse_net_contents_ml(expected)
    extracted_ml = _parse_net_contents_ml(extracted)

    if expected_ml is None or extracted_ml is None:
        return FieldResult(
            field="net_contents",
            status="FAIL",
            expected=expected,
            extracted=extracted,
            strategy=NET_CONTENTS_STRATEGY,
            score=None,
            message="Could not parse net contents.",
        )

    difference = abs(expected_ml - extracted_ml)
    status = "PASS" if difference <= 1 else "FAIL"

    return FieldResult(
        field="net_contents",
        status=status,
        expected=expected,
        extracted=extracted,
        strategy=NET_CONTENTS_STRATEGY,
        score=round(difference, 3),
        message=f"Net contents difference is {difference:.3f} ml; tolerance is 1.000 ml.",
    )


def compare_government_warning(expected: str, extracted: str | None) -> FieldResult:
    if _is_missing(extracted):
        return _missing_result("government_warning", expected, extracted, WARNING_STRATEGY)

    status = "PASS" if _normalize_warning_text(expected) == _normalize_warning_text(extracted) else "FAIL"

    return FieldResult(
        field="government_warning",
        status=status,
        expected=expected,
        extracted=extracted,
        strategy=WARNING_STRATEGY,
        score=100.0 if status == "PASS" else 0.0,
        message=(
            "Government warning must match exact wording, punctuation, and case; "
            "visual line wrapping is ignored."
        ),
    )


def _normalize_warning_text(value: str) -> str:
    return " ".join(value.split())


FIELD_COMPARISONS: tuple[
    tuple[str, Callable[[str, str | None], FieldResult]],
    ...
] = (
    ("brand_name", compare_brand_name),
    ("product_class", compare_product_class),
    ("producer_name", compare_producer_name),
    ("country_of_origin", compare_country_of_origin),
    ("alcohol_by_volume", compare_alcohol_by_volume),
    ("net_contents", compare_net_contents),
    ("government_warning", compare_government_warning),
)


def verify_label(application: ApplicationData, extracted: ExtractedLabel) -> VerificationResult:
    fields = [
        compare(getattr(application, field), getattr(extracted, field))
        for field, compare in FIELD_COMPARISONS
    ]
    verdict = "NEEDS_REVIEW" if any(field.status == "FAIL" for field in fields) else "PASS"

    return VerificationResult(verdict=verdict, fields=fields)
