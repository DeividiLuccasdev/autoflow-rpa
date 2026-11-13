"""Configuração de infraestrutura de teste; tarefas de negócio são as de produção."""

import os

from app.worker import celery_app

celery_app.conf.update(
    task_default_queue=os.environ["REQUEST_QUEUE"],
    broker_transport_options={"global_keyprefix": os.environ["REQUEST_PREFIX"]},
    beat_schedule={"dispatch-test": {"task": "app.worker.dispatch_pending", "schedule": 1.0}},
)
