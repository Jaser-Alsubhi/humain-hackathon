from sqlalchemy import func, select

from backend.models import JournalEntry, Order, Payment
from tests.test_items import make_client


def test_order_is_recorded_in_all_three_tables():
    client = make_client()
    r = client.post("/orders", json={"order_ref": "A-1", "amount_cents": 2500})
    assert r.status_code == 201
    assert r.json() == {"order_ref": "A-1", "amount_cents": 2500, "status": "paid"}
    assert client.get("/orders/A-1").json()["amount_cents"] == 2500
    assert client.get("/orders/summary").json() == {"journal": 1, "orders": 1, "payments": 1}


def test_repeating_an_order_ref_does_not_create_a_second_order():
    client = make_client()
    assert client.post("/orders", json={"order_ref": "A-2", "amount_cents": 100}).status_code == 201
    assert client.post("/orders", json={"order_ref": "A-2", "amount_cents": 100}).status_code == 200
    assert client.get("/orders/summary").json() == {"journal": 1, "orders": 1, "payments": 1}


def test_bad_input_is_rejected_and_unknown_order_is_404():
    client = make_client()
    assert client.post("/orders", json={"order_ref": "", "amount_cents": 100}).status_code == 422
    assert client.post("/orders", json={"order_ref": "A-3", "amount_cents": 0}).status_code == 422
    assert client.get("/orders/nope").status_code == 404
