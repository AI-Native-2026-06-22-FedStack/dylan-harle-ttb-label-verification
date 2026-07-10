import pytest
from pydantic import ValidationError

from app.models import FieldResult, VerificationResult


def test_verification_result_serializes_spec_contract_shape():
    result = VerificationResult(
        overall_verdict="APPROVED",
        results=[
            FieldResult(
                field="brand_name",
                status="PASS",
                expected="Acme Cellars",
                found="ACME CELLARS",
                match_type="fuzzy_token_set_ratio",
                score=100.0,
                message="Fuzzy score 100.00; threshold 90.00.",
            )
        ],
        latency_ms=1234,
    )

    payload = result.model_dump()

    assert set(payload) == {"overall_verdict", "results", "latency_ms"}
    assert payload["overall_verdict"] == "APPROVED"
    assert payload["latency_ms"] == 1234
    assert len(payload["results"]) == 1
    assert set(payload["results"][0]) == {
        "field",
        "status",
        "expected",
        "found",
        "match_type",
        "score",
        "message",
    }
    assert payload["results"][0]["field"] == "brand_name"
    assert payload["results"][0]["status"] == "PASS"
    assert payload["results"][0]["expected"] == "Acme Cellars"
    assert payload["results"][0]["found"] == "ACME CELLARS"
    assert payload["results"][0]["match_type"] == "fuzzy_token_set_ratio"


@pytest.mark.parametrize("verdict", ["APPROVED", "NEEDS_REVIEW"])
def test_verification_result_allows_spec_verdict_literals(verdict: str):
    result = VerificationResult(overall_verdict=verdict, results=[])

    assert result.overall_verdict == verdict


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_field_result_allows_field_status_literals(status: str):
    result = FieldResult(
        field="brand_name",
        status=status,
        expected="Acme Cellars",
        found="Different Brand",
        match_type="fuzzy_token_set_ratio",
        message="Compared field.",
    )

    assert result.status == status


def test_verification_result_rejects_old_pass_verdict_literal():
    with pytest.raises(ValidationError):
        VerificationResult(overall_verdict="PASS", results=[])
