import dataclasses
from decimal import Decimal

import pytest

from app.domain import (
    Customer, InvalidOrderData, InvalidOrderTransition, Money, Order, OrderItem,
    OrderItemLimitExceeded, OrderStatus,
)
from app.specifications import (
    ActivePromotionSpec, MinimumAmountSpec, MinimumUnitsSpec, VIPCustomerSpec,
    discount_rate, discounted_total, five_percent, ten_percent,
)
from cargar_csv import load_fixture


@pytest.fixture
def orders():
    return load_fixture()


def item(sku="SKU003", qty=1, price="120.00"):
    return OrderItem(sku, qty, Money(Decimal(price)))


# ---------------- Value Objects / invariantes
def test_money_negativo():
    with pytest.raises(InvalidOrderData):
        Money(Decimal("-1"))

def test_money_rechaza_float():
    with pytest.raises(InvalidOrderData):
        Money(600.0)

def test_money_rechaza_no_finito():
    with pytest.raises(InvalidOrderData):
        Money(Decimal("NaN"))

def test_money_inmutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Money(Decimal("1")).amount = Decimal("2")

def test_money_add_devuelve_nuevo_y_no_muta():
    a, b = Money(Decimal("100")), Money(Decimal("50"))
    assert a.add(b) == Money(Decimal("150"))
    assert a.amount == Decimal("100")

def test_money_monedas_distintas():
    with pytest.raises(InvalidOrderData):
        Money(Decimal("1")).add(Money(Decimal("1"), "USD"))

@pytest.mark.parametrize("qty", [0, -1])
def test_item_cantidad_invalida(qty):
    with pytest.raises(InvalidOrderData):
        item(qty=qty)

def test_item_subtotal_calculado():
    assert item("SKU001", 2, "600.00").subtotal.amount == Decimal("1200.00")


# ---------------- carga de datos
def test_carga_16_pedidos_todos_draft(orders):
    assert len(orders) == 16
    assert all(o.status == OrderStatus.DRAFT for o in orders.values())

def test_pedido_o001(orders):
    o = orders["O001"]
    assert o.units == 4 and o.total.amount == Decimal("2100.00")

def test_totales_manuales_manual(orders):
    assert orders["O006"].units == 1 and orders["O006"].total.amount == Decimal("18000.00")
    assert orders["O010"].units == 2 and orders["O010"].total.amount == Decimal("500.00")


# ---------------- límite de 20 unidades (suma de unidades, no renglones)
def test_21_unidades_rechazadas_sin_modificar(orders):
    o = orders["O009"]  # 19 unidades
    with pytest.raises(OrderItemLimitExceeded):
        o.add_item(item("SKU003", 2))
    assert o.units == 19 and len(o.items) == 1

def test_20_unidades_exactas_permitidas(orders):
    assert orders["O008"].units == 20
    orders["O008"].confirm()

def test_limite_cuenta_unidades_no_renglones():
    o = Order(Customer("X"), "T1")
    for _ in range(5):
        o.add_item(item(qty=4))  # 5 renglones, 20 unidades
    with pytest.raises(OrderItemLimitExceeded):
        o.add_item(item(qty=1))

def test_no_agrega_items_fuera_de_draft(orders):
    o = orders["O013"]; o.confirm()
    with pytest.raises(InvalidOrderTransition):
        o.add_item(item())


# ---------------- confirmación
def test_cliente_inactivo_no_confirma(orders):
    o = orders["O003"]
    with pytest.raises(InvalidOrderData):
        o.confirm()
    assert o.status == OrderStatus.DRAFT and o.events == []

def test_pedido_vacio_no_confirma(orders):
    o = orders["O007"]
    with pytest.raises(InvalidOrderData):
        o.confirm()
    assert o.status == OrderStatus.DRAFT and o.events == []

def test_confirmacion_doble(orders):
    o = orders["O013"]
    o.confirm()
    assert o.status == OrderStatus.CONFIRMED and [e.name for e in o.events] == ["OrderConfirmed"]
    with pytest.raises(InvalidOrderTransition):
        o.confirm()
    assert len(o.events) == 1  # el segundo intento NO agrega evento


# ---------------- envío / cancelación / entrega / devolución
@pytest.mark.parametrize("guia", ["", "   "])
def test_envio_sin_guia(orders, guia):
    o = orders["O012"]; o.confirm()
    with pytest.raises(InvalidOrderData):
        o.ship(guia)
    assert o.status == OrderStatus.CONFIRMED and [e.name for e in o.events] == ["OrderConfirmed"]

def test_no_envia_desde_draft(orders):
    with pytest.raises(InvalidOrderTransition):
        orders["O001"].ship("G1")

def test_cancelar_desde_shipped_prohibido(orders):
    o = orders["O014"]; o.confirm(); o.ship("G1")
    with pytest.raises(InvalidOrderTransition):
        o.cancel("ya no lo quiero")
    assert o.status == OrderStatus.SHIPPED
    assert [e.name for e in o.events] == ["OrderConfirmed", "OrderShipped"]

def test_cancelar_requiere_motivo(orders):
    o = orders["O014"]; o.confirm()
    with pytest.raises(InvalidOrderData):
        o.cancel(" ")
    assert o.status == OrderStatus.CONFIRMED

def test_cancelar_desde_confirmed(orders):
    o = orders["O014"]; o.confirm(); o.cancel("error de captura")
    assert o.status == OrderStatus.CANCELLED and o.events[-1].name == "OrderCancelled"

def test_flujo_entrega(orders):
    o = orders["O016"]; o.confirm(); o.ship("G1"); o.deliver()
    assert o.status == OrderStatus.DELIVERED
    assert [e.name for e in o.events] == ["OrderConfirmed", "OrderShipped", "OrderDelivered"]

def test_flujo_devolucion(orders):
    o = orders["O015"]; o.confirm(); o.ship("G1"); o.return_order()
    assert o.status == OrderStatus.RETURNED and o.events[-1].name == "OrderReturned"

def test_estados_terminales_no_avanzan(orders):
    o = orders["O016"]; o.confirm(); o.ship("G1"); o.deliver()
    for op in (o.confirm, lambda: o.ship("G"), lambda: o.cancel("x"), o.deliver, o.return_order):
        with pytest.raises(InvalidOrderTransition):
            op()

def test_eventos_son_inmutables_y_con_timestamp(orders):
    o = orders["O013"]; o.confirm()
    e = o.events[0]
    assert e.order_id == "O013" and e.occurred_at.tzinfo is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.name = "otro"


# ---------------- Specifications y descuentos
@pytest.mark.parametrize("pid,tasa", [
    ("O001", "0.10"),  # E01 VIP, 2100, 4 u, sin promo
    ("O002", "0"),     # E02 no VIP, < 5000
    ("O005", "0"),     # E04 promoción bloquea
    ("O006", "0.05"),  # E05 > 5000 sin promo
    ("O010", "0"),     # E09 total == 500 no supera
    ("O011", "0"),     # E10 solo 3 unidades
])
def test_descuentos_escenarios(orders, pid, tasa):
    assert discount_rate(orders[pid]) == Decimal(tasa)

def test_total_con_descuento_no_modifica_pedido(orders):
    o = orders["O001"]
    assert discounted_total(o).amount == Decimal("1890.00")
    assert o.total.amount == Decimal("2100.00")

def test_prioridad_10_sobre_5():
    o = Order(Customer("V", is_vip=True), "T2")
    o.add_item(item("SKU008", 1, "6000.00")); o.add_item(item("SKU003", 3, "120.00"))
    assert five_percent.is_satisfied_by(o) and ten_percent.is_satisfied_by(o)
    assert discount_rate(o) == Decimal("0.10")

def test_specs_simples_y_composicion(orders):
    o = orders["O010"]
    assert not MinimumAmountSpec(Decimal("500")).is_satisfied_by(o)       # estricto
    assert MinimumAmountSpec(Decimal("499.99")).is_satisfied_by(o)
    assert not VIPCustomerSpec().is_satisfied_by(o)
    assert MinimumUnitsSpec(2).is_satisfied_by(o) and not MinimumUnitsSpec(3).is_satisfied_by(o)
    assert (~ActivePromotionSpec()).is_satisfied_by(o)
    assert (VIPCustomerSpec() | MinimumUnitsSpec(2)).is_satisfied_by(o)   # OR
    assert not (VIPCustomerSpec() & MinimumUnitsSpec(2)).is_satisfied_by(o)  # AND

def test_spec_no_modifica_pedido(orders):
    o = orders["O001"]; antes = (o.status, o.units, o.total, len(o.events))
    ten_percent.is_satisfied_by(o)
    assert antes == (o.status, o.units, o.total, len(o.events))
