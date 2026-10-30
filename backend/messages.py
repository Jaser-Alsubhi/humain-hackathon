"""A message queue with a background worker.

POST /queue/messages journals the message first, then offers it to a bounded queue (a table). A worker thread takes
messages off the queue and processes them. What happens when the queue is full is configuration:
  QUEUE_OVERFLOW=reject (default): answer 429, so the sender knows and retries.
  QUEUE_OVERFLOW=drop: answer 202 anyway and discard the message. This is the unsafe setting. Only the journal remembers it.
QUEUE_MAX_DEPTH bounds the queue. WORKER_DELAY_MS slows the worker (default 0)."""
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from backend.db import SessionLocal, get_db
from backend.models import QueueDone, QueueJournal, QueueMessage

router = APIRouter(prefix="/queue", tags=["queue"])


def settings():
    return {"max_depth": int(os.getenv("QUEUE_MAX_DEPTH", "1000")),
            "overflow": os.getenv("QUEUE_OVERFLOW", "reject"),
            "delay_ms": int(os.getenv("WORKER_DELAY_MS", "0"))}


class MessageIn(BaseModel):
    msg_ref: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0)


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def _offer(db, msg_ref, amount_cents):
    """Put one journaled message on the queue. Returns queued, dropped or full."""
    cfg = settings()
    if _count(db, QueueMessage) >= cfg["max_depth"]:
        return "dropped" if cfg["overflow"] == "drop" else "full"
    db.execute(insert(QueueMessage).values(msg_ref=msg_ref, amount_cents=amount_cents))
    return "queued"


@router.post("/messages", status_code=202)
def enqueue(body: MessageIn, db: Session = Depends(get_db)):
    """Accept a message. msg_ref is the sender's idempotency key."""
    if db.scalar(select(QueueJournal.id).where(QueueJournal.msg_ref == body.msg_ref)):
        return {"status": "accepted"}
    cfg = settings()
    if cfg["overflow"] != "drop" and _count(db, QueueMessage) >= cfg["max_depth"]:
        raise HTTPException(status_code=429, detail="Queue is full, retry later")
    db.execute(insert(QueueJournal).values(msg_ref=body.msg_ref, amount_cents=body.amount_cents))
    _offer(db, body.msg_ref, body.amount_cents)
    db.commit()
    return {"status": "accepted"}


def _lost_rows(db):
    return db.execute(
        select(QueueJournal.msg_ref, QueueJournal.amount_cents)
        .outerjoin(QueueMessage, QueueMessage.msg_ref == QueueJournal.msg_ref)
        .outerjoin(QueueDone, QueueDone.msg_ref == QueueJournal.msg_ref)
        .where(QueueMessage.msg_ref.is_(None), QueueDone.msg_ref.is_(None))
        .order_by(QueueJournal.id)).all()


@router.post("/replay")
def replay(db: Session = Depends(get_db)):
    """Offer every journaled message that is neither queued nor processed to the queue again, under the current settings."""
    result = {"queued": 0, "dropped": 0, "full": 0}
    for msg_ref, amount_cents in _lost_rows(db):
        result[_offer(db, msg_ref, amount_cents)] += 1
    db.commit()
    return result


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return {"journal": _count(db, QueueJournal), "queued": _count(db, QueueMessage),
            "done": _count(db, QueueDone), "lost": len(_lost_rows(db)), "settings": settings()}


def work_once():
    """Process the oldest queued message. Returns the seconds to pause before the next one."""
    try:
        with SessionLocal() as db:
            msg = db.scalar(select(QueueMessage).order_by(QueueMessage.id).limit(1))
            if msg is None:
                return 0.2
            if not db.scalar(select(QueueDone.id).where(QueueDone.msg_ref == msg.msg_ref)):
                db.add(QueueDone(msg_ref=msg.msg_ref, amount_cents=msg.amount_cents))
            db.delete(msg)
            db.commit()
            return settings()["delay_ms"] / 1000
    except Exception:
        return 1.0


def run_worker(stop):
    while not stop.is_set():
        time.sleep(work_once())


def start_worker():
    """Start the worker thread unless QUEUE_WORKER=0. Returns the event that stops it."""
    stop = threading.Event()
    if os.getenv("QUEUE_WORKER", "1") == "1":
        threading.Thread(target=run_worker, args=(stop,), daemon=True).start()
    return stop
