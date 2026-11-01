import os
import logging
from datetime import datetime, timezone
from celery import Celery
from sqlalchemy import select
from .db import SessionLocal
from .models import Execution
from .executions import expire_exhausted, process_execution, record_failure, reserve_dispatch

logger = logging.getLogger(__name__)

celery_app = Celery("autoflow", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC",
                       worker_prefetch_multiplier=1, task_soft_time_limit=30, task_time_limit=45,
                       task_publish_retry=False, broker_connection_timeout=5)
celery_app.conf.beat_schedule = {"dispatch-pending": {"task": "app.worker.dispatch_pending", "schedule": 10.0}}

@celery_app.task
def healthcheck():
    return {"status": "ok"}

@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def process_document(execution_id):
    with SessionLocal() as db:
        try:
            process_execution(db, execution_id)
        except Exception:
            db.rollback()
            record_failure(db, execution_id)
            logger.error("execution_processing_failed execution_id=%s", execution_id)
            raise

@celery_app.task
def dispatch_pending():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        expire_exhausted(db, now)
        ids = db.scalars(select(Execution.id).where(Execution.status == "queued", Execution.next_dispatch_at <= now).order_by(Execution.created_at).limit(100)).all()
    count = 0
    for execution_id in ids:
        with SessionLocal() as db:
            if not reserve_dispatch(db, execution_id, now):
                continue
        try:
            process_document.delay(execution_id)
            count += 1
        except Exception:
            logger.error("execution_publish_failed execution_id=%s", execution_id)
    return count
