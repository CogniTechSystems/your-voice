from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbDep, get_or_404
from app.models import WritingSample
from app.schemas.samples import SampleRead, SampleSummary, SampleWrite

router = APIRouter(prefix="/samples", tags=["writing samples"])


def _apply(sample: WritingSample, payload: SampleWrite) -> None:
    sample.title = payload.title.strip()
    sample.format = payload.format
    sample.content = payload.content
    sample.notes = payload.notes.strip()


@router.get("", response_model=list[SampleSummary])
def list_samples(db: DbDep) -> list[SampleSummary]:
    samples = db.scalars(select(WritingSample).order_by(WritingSample.title))
    return [SampleSummary.from_sample(sample) for sample in samples]


@router.post("", response_model=SampleRead, status_code=status.HTTP_201_CREATED)
def create_sample(payload: SampleWrite, db: DbDep) -> SampleRead:
    sample = WritingSample()
    _apply(sample, payload)
    db.add(sample)
    db.commit()
    return SampleRead.from_sample(sample)


@router.get("/{sample_id}", response_model=SampleRead)
def get_sample(sample_id: int, db: DbDep) -> SampleRead:
    return SampleRead.from_sample(get_or_404(db, WritingSample, sample_id))


@router.put("/{sample_id}", response_model=SampleRead)
def update_sample(sample_id: int, payload: SampleWrite, db: DbDep) -> SampleRead:
    sample = get_or_404(db, WritingSample, sample_id)
    _apply(sample, payload)
    db.commit()
    return SampleRead.from_sample(sample)


@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sample(sample_id: int, db: DbDep) -> None:
    db.delete(get_or_404(db, WritingSample, sample_id))
    db.commit()
