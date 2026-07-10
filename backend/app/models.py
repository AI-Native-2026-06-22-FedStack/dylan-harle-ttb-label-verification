from typing import Literal

from pydantic import BaseModel


FieldStatus = Literal["PASS", "FAIL"]
Verdict = Literal["APPROVED", "NEEDS_REVIEW"]
BatchItemStatus = Literal["APPROVED", "NEEDS_REVIEW", "ERROR"]


class ApplicationData(BaseModel):
    brand_name: str
    class_type: str
    producer: str
    country_of_origin: str
    abv: str
    net_contents: str
    government_warning: str


class ExtractedLabel(BaseModel):
    brand_name: str | None = None
    class_type: str | None = None
    producer: str | None = None
    country_of_origin: str | None = None
    abv: str | None = None
    net_contents: str | None = None
    government_warning: str | None = None
    raw_text: str | None = None
    extraction_confidence: float | None = None


class FieldResult(BaseModel):
    field: str
    status: FieldStatus
    expected: str
    found: str | None
    match_type: str
    score: float | None = None
    message: str


class VerificationResult(BaseModel):
    overall_verdict: Verdict
    results: list[FieldResult]
    latency_ms: int | None = None


class BatchError(BaseModel):
    code: str
    message: str


class BatchSummary(BaseModel):
    total: int
    passed: int
    needs_review: int


class BatchItemResult(BaseModel):
    index: int
    filename: str
    status: BatchItemStatus
    result: VerificationResult | None = None
    error: BatchError | None = None
    latency_ms: int | None = None


class BatchVerificationResult(BaseModel):
    summary: BatchSummary
    items: list[BatchItemResult]
    latency_ms: int
