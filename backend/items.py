from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Item

router = APIRouter(prefix="/items", tags=["items"])


class ItemIn(BaseModel):
    text: str
    label: str | None = None


class ItemOut(ItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


@router.post("", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, db: Session = Depends(get_db)):
    item = Item(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[ItemOut])
def list_items(db: Session = Depends(get_db)):
    return db.scalars(select(Item).order_by(Item.id)).all()


@router.get("/{item_id}", response_model=ItemOut)
def read_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
