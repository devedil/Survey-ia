from sqlalchemy.orm import Session

from backend.app.usage.models import ModelUsage


def record_usage(db: Session, usage: ModelUsage) -> None:
    db.add(usage)
    db.commit()
