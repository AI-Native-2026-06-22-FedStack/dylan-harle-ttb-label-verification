import pytest

from app.comparison import (
    compare_alcohol_by_volume,
    compare_brand_name,
    compare_country_of_origin,
    compare_government_warning,
    compare_net_contents,
    verify_label,
)
from app.models import ApplicationData, ExtractedLabel


WARNING = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH "
    "DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO "
    "DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)


def application_data(**overrides: str) -> ApplicationData:
    data = {
        "brand_name": "Acme Cellars",
        "product_class": "Red Wine",
        "producer_name": "Acme Winery LLC",
        "country_of_origin": "United States",
        "alcohol_by_volume": "13.5%",
        "net_contents": "750 mL",
        "government_warning": WARNING,
    }
    data.update(overrides)
    return ApplicationData(**data)


def extracted_label(**overrides: str | None) -> ExtractedLabel:
    data = {
        "brand_name": "ACME CELLARS",
        "product_class": "Red wine",
        "producer_name": "Acme Winery, LLC",
        "country_of_origin": "USA",
        "alcohol_by_volume": "13.5% Alc./Vol.",
        "net_contents": "750ml",
        "government_warning": WARNING,
    }
    data.update(overrides)
    return ExtractedLabel(**data)


@pytest.mark.parametrize(
    ("field", "expected", "extracted"),
    [
        ("brand_name", "Acme Cellars", None),
        ("brand_name", "Acme Cellars", "   "),
        ("product_class", "Red Wine", None),
        ("product_class", "Red Wine", "   "),
        ("producer_name", "Acme Winery LLC", None),
        ("producer_name", "Acme Winery LLC", "   "),
        ("country_of_origin", "United States", None),
        ("country_of_origin", "United States", "   "),
        ("alcohol_by_volume", "13.5%", None),
        ("alcohol_by_volume", "13.5%", "   "),
        ("net_contents", "750 mL", None),
        ("net_contents", "750 mL", "   "),
        ("government_warning", WARNING, None),
        ("government_warning", WARNING, "   "),
    ],
)
def test_missing_or_blank_extracted_value_fails(field, expected, extracted):
    app_data = application_data(**{field: expected})
    label = extracted_label(**{field: extracted})

    result = verify_label(app_data, label)
    field_result = next(item for item in result.fields if item.field == field)

    assert field_result.status == "FAIL"
    assert field_result.extracted == extracted
    assert result.verdict == "NEEDS_REVIEW"


def test_case_only_brand_difference_passes():
    result = compare_brand_name("Acme Cellars", "ACME CELLARS")

    assert result.status == "PASS"


def test_abv_ignores_proof_when_percentage_matches():
    result = compare_alcohol_by_volume("45%", "45% Alc./Vol. (90 Proof)")

    assert result.status == "PASS"


def test_net_contents_normalizes_spacing_and_unit_case():
    result = compare_net_contents("750 mL", "750ml")

    assert result.status == "PASS"


def test_country_synonym_usa_matches_united_states():
    result = compare_country_of_origin("USA", "United States")

    assert result.status == "PASS"


def test_government_warning_title_case_fails():
    title_case_warning = WARNING.title()

    result = compare_government_warning(WARNING, title_case_warning)

    assert result.status == "FAIL"


def test_government_warning_missing_colon_fails():
    warning_without_colon = WARNING.replace("GOVERNMENT WARNING:", "GOVERNMENT WARNING")

    result = compare_government_warning(WARNING, warning_without_colon)

    assert result.status == "FAIL"


def test_correct_all_caps_government_warning_passes():
    result = compare_government_warning(WARNING, WARNING)

    assert result.status == "PASS"


def test_misread_government_warning_returns_extracted_text():
    misread_warning = WARNING.replace("SURGEON", "SUREEON")

    result = compare_government_warning(WARNING, misread_warning)

    assert result.status == "FAIL"
    assert result.extracted == misread_warning


def test_all_fields_pass_returns_pass_verdict():
    result = verify_label(application_data(), extracted_label())

    assert result.verdict == "PASS"
    assert len(result.fields) == 7
    assert all(field.status == "PASS" for field in result.fields)


def test_any_failed_field_returns_needs_review():
    result = verify_label(application_data(), extracted_label(brand_name="Different Brand"))

    assert result.verdict == "NEEDS_REVIEW"
    assert any(field.status == "FAIL" for field in result.fields)

