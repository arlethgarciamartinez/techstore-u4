# TechStore U4 — Núcleo de negocio de pedidos

Práctica guiada de CLN · Unidad 4 (FIME-UANL). Entidades y Value Objects, Specification Pattern,
máquina de estados con Domain Events y API REST con FastAPI. Todo en memoria (sin base de datos).

## Instalación

```bash
python --version            # 3.11+
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
python -m pip install fastapi uvicorn pytest httpx
```

## Ejecución

```bash
python cargar_csv.py        # carga los 16 pedidos (todos DRAFT)
python escenarios.py        # ejecuta E01–E15 y muestra la bitácora
python -m pytest -q         # 54 pruebas
uvicorn app.api:app --reload  # http://127.0.0.1:8000/docs
```

## Estructura

```
datos/            CSV del paquete (clientes, productos, pedidos, detalle, escenarios)
cargar_csv.py     cargador del paquete (sin modificar)
escenarios.py     ejecuta E01–E15
app/domain.py     Money, Customer, OrderItem, Order, OrderStatus, DomainEvent, excepciones
app/specifications.py  Specification, And/Or/Not y reglas de descuento
app/api.py        API FastAPI (controlador delgado)
tests/            pytest: dominio y API
evidencias/       capturas y salidas de terminal
```

## Reglas de negocio

- `Money`: inmutable, `Decimal`, no admite importes negativos ni float.
- Máximo **20 unidades** por pedido (suma de cantidades, no renglones).
- **Descuento 10 %**: cliente VIP **y** total > 500 **y** ≥ 4 unidades **y** sin promoción.
- **Descuento 5 %**: total > 5000 **y** sin promoción. Si se cumplen ambas, gana el 10 %.
- Confirmar: solo desde DRAFT, con artículos y cliente activo.
- Enviar: solo desde CONFIRMED y con guía no vacía. Cancelar: solo desde CONFIRMED y con motivo.
- Entregar / devolver: solo desde SHIPPED.
- Una operación rechazada no cambia el estado ni agrega eventos.

```
DRAFT --confirm--> CONFIRMED --ship--> SHIPPED --deliver--> DELIVERED
                      |                   |
                    cancel              return
                      v                   v
                  CANCELLED            RETURNED
```

Eventos: `OrderConfirmed`, `OrderShipped`, `OrderCancelled`, `OrderDelivered`, `OrderReturned`.

## Endpoints

| Método | Ruta | Éxito | Errores |
|---|---|---|---|
| GET | `/orders` | 200 | |
| GET | `/orders/{id}` | 200 | 404 |
| POST | `/orders/{id}/items` | 201 | 404, 409 (no DRAFT), 422 (>20 u. / dato inválido) |
| POST | `/orders/{id}/confirm` | 200 | 404, 409 (transición), 422 (vacío / cliente inactivo) |
| POST | `/orders/{id}/ship` `{tracking_number}` | 200 | 404, 409, 422 (sin guía) |
| POST | `/orders/{id}/cancel` `{reason}` | 200 | 404, 409, 422 (sin motivo) |
| POST | `/orders/{id}/deliver` | 200 | 404, 409 |
| POST | `/orders/{id}/return` | 200 | 404, 409 |

Mapeo de excepciones: `InvalidOrderTransition` → 409; `InvalidOrderData` / `OrderItemLimitExceeded` → 422;
pedido inexistente → 404. El controlador no contiene reglas de negocio.
