"""API REST (controlador delgado): busca el pedido, llama al dominio y traduce excepciones a HTTP."""
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.domain import (
    DomainException,
    InvalidOrderData,
    InvalidOrderTransition,
    Money,
    Order,
    OrderItem,
    OrderItemLimitExceeded,
)
from app.specifications import discount_rate, discounted_total
from cargar_csv import load_fixture

app = FastAPI(title="TechStore U4", description="Núcleo de negocio de pedidos (en memoria)")
orders = load_fixture()


class ShipRequest(BaseModel):
    tracking_number: str


class CancelRequest(BaseModel):
    reason: str


class ItemRequest(BaseModel):
    sku: str
    quantity: int
    unit_price_mxn: Decimal


def to_dto(order: Order) -> dict:
    return {
        "id": order.id,
        "customer_id": order.customer.id,
        "status": order.status.value,
        "units": order.units,
        "total_mxn": str(order.total.amount),
        "discount_rate": str(discount_rate(order)),
        "total_with_discount_mxn": str(discounted_total(order).amount),
        "tracking_number": order.tracking_number,
        "events": [e.name for e in order.events],
    }


def get_order(order_id: str) -> Order:
    order = orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"No existe el pedido {order_id}")
    return order


def run(order_id: str, operation):
    """Ejecuta una operación del dominio y traduce las excepciones a códigos HTTP."""
    order = get_order(order_id)
    try:
        operation(order)
    except InvalidOrderTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (InvalidOrderData, OrderItemLimitExceeded) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DomainException as exc:  # cualquier otra regla de negocio
        raise HTTPException(status_code=400, detail=str(exc))
    return to_dto(order)


@app.get("/orders")
def list_orders():
    return [to_dto(o) for o in orders.values()]


@app.get("/orders/{order_id}")
def read_order(order_id: str):
    return to_dto(get_order(order_id))


@app.post("/orders/{order_id}/items", status_code=201)
def add_item(order_id: str, body: ItemRequest):
    return run(
        order_id,
        lambda o: o.add_item(OrderItem(body.sku, body.quantity, Money(body.unit_price_mxn))),
    )


@app.post("/orders/{order_id}/confirm")
def confirm_order(order_id: str):
    return run(order_id, lambda o: o.confirm())


@app.post("/orders/{order_id}/ship")
def ship_order(order_id: str, body: ShipRequest):
    return run(order_id, lambda o: o.ship(body.tracking_number))


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, body: CancelRequest):
    return run(order_id, lambda o: o.cancel(body.reason))


@app.post("/orders/{order_id}/deliver")
def deliver_order(order_id: str):
    return run(order_id, lambda o: o.deliver())


@app.post("/orders/{order_id}/return")
def return_order(order_id: str):
    return run(order_id, lambda o: o.return_order())
