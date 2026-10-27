from datetime import datetime

from pydantic import Field

from app.models import DocumentFormat, WritingSample
from app.schemas.base import Schema

EXCERPT_LENGTH = 240


class SampleWrite(Schema):
    title: str = Field(min_length=1, max_length=200)
    format: DocumentFormat = DocumentFormat.MARKDOWN
    content: str = Field(min_length=1, max_length=500_000)
    notes: str = Field(default="", max_length=2000)


class SampleSummary(Schema):
    id: int
    title: str
    format: DocumentFormat
    notes: str
    word_count: int
    excerpt: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_sample(cls, sample: WritingSample) -> "SampleSummary":
        return cls(
            id=sample.id,
            title=sample.title,
            format=sample.format,
            notes=sample.notes,
            word_count=sample.word_count,
            excerpt=" ".join(sample.content.split())[:EXCERPT_LENGTH],
            created_at=sample.created_at,
            updated_at=sample.updated_at,
        )


class SampleRead(SampleSummary):
    content: str

    @classmethod
    def from_sample(cls, sample: WritingSample) -> "SampleRead":
        return cls(**SampleSummary.from_sample(sample).model_dump(), content=sample.content)
