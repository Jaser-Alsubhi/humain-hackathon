from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import JournalEntry, Order, Payment

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderIn(BaseModel):
    order_ref: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0)


class OrderOut(OrderIn):
    status: str


@router.post("", response_model=OrderOut, status_code=201)
def create_order(body: OrderIn, response: Response, db: Session = Depends(get_db)):
    """Take an order and its payment. order_ref is the client's idempotency key: a repeat returns 200, not a second order."""
    if db.scalar(select(JournalEntry.id).where(JournalEntry.order_ref == body.order_ref)):
        response.status_code = 200
        return OrderOut(**body.model_dump(), status="paid")
    values = {"order_ref": body.order_ref, "amount_cents": body.amount_cents}
    db.execute(insert(JournalEntry).values(**values))
    db.execute(insert(Order).values(**values, status="paid"))
    db.execute(insert(Payment).values(**values))
    db.commit()
    return OrderOut(**values, status="paid")


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    count = lambda model: db.scalar(select(func.count()).select_from(model))  # noqa: E731
    return {"journal": count(JournalEntry), "orders": count(Order), "payments": count(Payment)}


@router.get("/{order_ref}", response_model=OrderOut)
def read_order(order_ref: str, db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.order_ref == order_ref))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderOut(order_ref=order.order_ref, amount_cents=order.amount_cents, status=order.status)
