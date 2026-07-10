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


def _missing_result(field: str, expected: str, found: str | None, match_type: str) -> FieldResult:
    return FieldResult(
        field=field,
        status="FAIL",
        expected=expected,
        found=found,
        match_type=match_type,
        score=None,
        message="Extracted value is missing.",
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _token_set_ratio(expected: str, found: str) -> float:
    expected_tokens = set(re.findall(r"[a-z0-9]+", expected.casefold()))
    found_tokens = set(re.findall(r"[a-z0-9]+", found.casefold()))

    if not expected_tokens and not found_tokens:
        return 100.0
    if expected_tokens == found_tokens:
        return 100.0

    expected_joined = " ".join(sorted(expected_tokens))
    found_joined = " ".join(sorted(found_tokens))

    return float(fuzz.token_set_ratio(expected_joined, found_joined))


def _compare_fuzzy(
    field: str,
    expected: str,
    found: str | None,
    threshold: float,
) -> FieldResult:
    if _is_missing(found):
        return _missing_result(field, expected, found, FUZZY_STRATEGY)

    score = _token_set_ratio(_normalize_text(expected), _normalize_text(found))
    status = "PASS" if score >= threshold else "FAIL"

    return FieldResult(
        field=field,
        status=status,
        expected=expected,
        found=found,
        match_type=FUZZY_STRATEGY,
        score=round(score, 2),
        message=f"Fuzzy score {score:.2f}; threshold {threshold:.2f}.",
    )


def compare_brand_name(expected: str, found: str | None) -> FieldResult:
    return _compare_fuzzy("brand_name", expected, found, threshold=90)


def compare_class_type(expected: str, found: str | None) -> FieldResult:
    return _compare_fuzzy("class_type", expected, found, threshold=88)


def compare_producer(expected: str, found: str | None) -> FieldResult:
    return _compare_fuzzy("producer", expected, found, threshold=90)


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


def compare_country_of_origin(expected: str, found: str | None) -> FieldResult:
    if _is_missing(found):
        return _missing_result("country_of_origin", expected, found, COUNTRY_STRATEGY)

    expected_country = _canonical_country(expected)
    found_country = _canonical_country(found)
    status = "PASS" if expected_country == found_country else "FAIL"

    return FieldResult(
        field="country_of_origin",
        status=status,
        expected=expected,
        found=found,
        match_type=COUNTRY_STRATEGY,
        score=100.0 if status == "PASS" else 0.0,
        message=f"Expected canonical country '{expected_country}', got '{found_country}'.",
    )


def _parse_percentage(value: str) -> float | None:
    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    if percent_match:
        return float(percent_match.group(1))

    proof_match = re.search(r"(\d+(?:\.\d+)?)\s*proof", value, re.IGNORECASE)
    if proof_match:
        return float(proof_match.group(1)) / 2

    number_match = re.search(r"\d+(?:\.\d+)?", value)
    if number_match:
        return float(number_match.group(0))

    return None


def compare_abv(expected: str, found: str | None) -> FieldResult:
    if _is_missing(found):
        return _missing_result("abv", expected, found, ABV_STRATEGY)

    expected_value = _parse_percentage(expected)
    found_value = _parse_percentage(found)

    if expected_value is None or found_value is None:
        return FieldResult(
            field="abv",
            status="FAIL",
            expected=expected,
            found=found,
            match_type=ABV_STRATEGY,
            score=None,
            message="Could not parse ABV percentage.",
        )

    difference = abs(expected_value - found_value)
    status = "PASS" if difference <= 0.1 else "FAIL"

    return FieldResult(
        field="abv",
        status=status,
        expected=expected,
        found=found,
        match_type=ABV_STRATEGY,
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
    "centiliter": 10.0,
    "centiliters": 10.0,
    "fl oz": 29.5735295625,
    "fluid ounce": 29.5735295625,
    "fluid ounces": 29.5735295625,
    "oz": 29.5735295625,
}


def _parse_net_contents_ml(value: str) -> float | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(fl\s*oz|fluid\s*ounces?|ml|milliliters?|l|liters?|cl|centiliters?|oz)\b",
        value,
        re.IGNORECASE,
    )
    if not match:
        return None

    amount = float(match.group(1))
    unit = " ".join(match.group(2).casefold().split())
    multiplier = UNIT_TO_ML.get(unit)

    if multiplier is None:
        return None

    return amount * multiplier


def compare_net_contents(expected: str, found: str | None) -> FieldResult:
    if _is_missing(found):
        return _missing_result("net_contents", expected, found, NET_CONTENTS_STRATEGY)

    expected_ml = _parse_net_contents_ml(expected)
    found_ml = _parse_net_contents_ml(found)

    if expected_ml is None or found_ml is None:
        return FieldResult(
            field="net_contents",
            status="FAIL",
            expected=expected,
            found=found,
            match_type=NET_CONTENTS_STRATEGY,
            score=None,
            message="Could not parse net contents.",
        )

    difference = abs(expected_ml - found_ml)
    status = "PASS" if difference <= 1 else "FAIL"

    return FieldResult(
        field="net_contents",
        status=status,
        expected=expected,
        found=found,
        match_type=NET_CONTENTS_STRATEGY,
        score=round(difference, 3),
        message=f"Net contents difference is {difference:.3f} ml; tolerance is 1.000 ml.",
    )


def compare_government_warning(expected: str, found: str | None) -> FieldResult:
    if _is_missing(found):
        return _missing_result("government_warning", expected, found, WARNING_STRATEGY)

    status = "PASS" if _normalize_warning_text(expected) == _normalize_warning_text(found) else "FAIL"

    return FieldResult(
        field="government_warning",
        status=status,
        expected=expected,
        found=found,
        match_type=WARNING_STRATEGY,
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
    ("class_type", compare_class_type),
    ("producer", compare_producer),
    ("country_of_origin", compare_country_of_origin),
    ("abv", compare_abv),
    ("net_contents", compare_net_contents),
    ("government_warning", compare_government_warning),
)


def verify_label(application: ApplicationData, extracted: ExtractedLabel) -> VerificationResult:
    results = [
        compare(getattr(application, field), getattr(extracted, field))
        for field, compare in FIELD_COMPARISONS
    ]
    verdict = "NEEDS_REVIEW" if any(field.status == "FAIL" for field in results) else "APPROVED"

    return VerificationResult(overall_verdict=verdict, results=results)
