import pytest
from fastapi.testclient import TestClient

from app import api
from cargar_csv import load_fixture


@pytest.fixture
def client():
    api.orders.clear(); api.orders.update(load_fixture())  # estado fresco por prueba
    return TestClient(api.app)


def test_404_pedido_inexistente(client):
    assert client.post("/orders/NOPE/confirm").status_code == 404
    assert client.get("/orders/NOPE").status_code == 404

def test_get_pedido_con_descuento(client):
    r = client.get("/orders/O001")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "DRAFT" and d["units"] == 4 and d["total_mxn"] == "2100.00"
    assert d["discount_rate"] == "0.10" and d["total_with_discount_mxn"] == "1890.00"

def test_listado_16(client):
    assert len(client.get("/orders").json()) == 16

def test_confirmar_ok(client):
    r = client.post("/orders/O013/confirm")
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"
    assert r.json()["events"] == ["OrderConfirmed"]

def test_confirmar_dos_veces_409(client):
    client.post("/orders/O013/confirm")
    r = client.post("/orders/O013/confirm")
    assert r.status_code == 409
    assert client.get("/orders/O013").json()["events"] == ["OrderConfirmed"]

def test_confirmar_vacio_422(client):
    assert client.post("/orders/O007/confirm").status_code == 422

def test_confirmar_cliente_inactivo_422(client):
    assert client.post("/orders/O003/confirm").status_code == 422

def test_envio_sin_guia_422(client):
    client.post("/orders/O012/confirm")
    assert client.post("/orders/O012/ship", json={"tracking_number": ""}).status_code == 422
    assert client.get("/orders/O012").json()["status"] == "CONFIRMED"

def test_flujo_completo_entrega(client):
    assert client.post("/orders/O016/confirm").status_code == 200
    r = client.post("/orders/O016/ship", json={"tracking_number": "G-1"})
    assert r.status_code == 200 and r.json()["tracking_number"] == "G-1"
    r = client.post("/orders/O016/deliver")
    assert r.json()["status"] == "DELIVERED"

def test_cancelar_desde_shipped_409(client):
    client.post("/orders/O014/confirm"); client.post("/orders/O014/ship", json={"tracking_number": "G"})
    assert client.post("/orders/O014/cancel", json={"reason": "x"}).status_code == 409

def test_cancelar_ok(client):
    client.post("/orders/O014/confirm")
    r = client.post("/orders/O014/cancel", json={"reason": "error"})
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"

def test_devolucion(client):
    client.post("/orders/O015/confirm"); client.post("/orders/O015/ship", json={"tracking_number": "G"})
    assert client.post("/orders/O015/return").json()["status"] == "RETURNED"

def test_agregar_item_21_unidades_422(client):
    r = client.post("/orders/O009/items", json={"sku": "SKU003", "quantity": 2, "unit_price_mxn": "120.00"})
    assert r.status_code == 422
    assert client.get("/orders/O009").json()["units"] == 19

def test_agregar_item_ok_201(client):
    r = client.post("/orders/O009/items", json={"sku": "SKU003", "quantity": 1, "unit_price_mxn": "120.00"})
    assert r.status_code == 201 and r.json()["units"] == 20

def test_body_invalido_422(client):
    assert client.post("/orders/O012/ship", json={}).status_code == 422
