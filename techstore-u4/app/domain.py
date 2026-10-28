"""Núcleo de dominio TechStore U4: Value Objects, entidades, máquina de estados y eventos.

No depende de FastAPI ni de ninguna infraestructura: se puede ejecutar y probar en memoria.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

MAX_UNITS = 20


# ---------------------------------------------------------------- excepciones
class DomainException(Exception):
    """Violación de una regla de negocio (no es un error técnico)."""


class OrderException(DomainException):
    pass


class InvalidOrderData(OrderException):
    """Dato inválido o precondición de negocio no cumplida (-> HTTP 422)."""


class InvalidOrderTransition(OrderException):
    """Transición de estado no permitida (-> HTTP 409)."""

    def __init__(self, current, action):
        super().__init__(f"No se puede {action} un pedido en estado {current}")
        self.current = current
        self.action = action


class OrderItemLimitExceeded(OrderException):
    """Se supera el máximo de 20 unidades por pedido (-> HTTP 422)."""

    def __init__(self, attempted=None):
        detalle = f" (intento: {attempted})" if attempted is not None else ""
        super().__init__(f"Un pedido no puede tener más de {MAX_UNITS} unidades{detalle}")


# ------------------------------------------------------------- value objects
@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "MXN"

    def __post_init__(self):
        if not isinstance(self.amount, Decimal):
            raise InvalidOrderData("El monto debe ser Decimal, no float/int")
        if not self.amount.is_finite() or self.amount < 0:
            raise InvalidOrderData("Monto inválido")

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise InvalidOrderData("Monedas distintas")
        return Money(self.amount + other.amount, self.currency)

    def multiply(self, factor) -> "Money":
        return Money(self.amount * Decimal(factor), self.currency)


@dataclass(frozen=True)
class Customer:
    id: str
    is_vip: bool = False
    active: bool = True


@dataclass(frozen=True)
class OrderItem:
    sku: str
    quantity: int
    unit_price: Money

    def __post_init__(self):
        if not self.sku.strip() or self.quantity <= 0:
            raise InvalidOrderData("Artículo inválido")

    @property
    def subtotal(self) -> Money:
        return Money(self.unit_price.amount * self.quantity, self.unit_price.currency)


# ------------------------------------------------------------------- eventos
@dataclass(frozen=True)
class DomainEvent:
    name: str
    order_id: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ----------------------------------------------------------- estado y Order
class OrderStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"


@dataclass
class Order:
    """Aggregate Root: concentra invariantes y transiciones del pedido.

    Regla de oro de cada transición: 1) validar, 2) cambiar status, 3) registrar evento.
    Si algo falla antes del paso 2, ni el estado ni los eventos cambian.
    """

    customer: Customer
    id: str
    has_promotion: bool = False
    status: OrderStatus = OrderStatus.DRAFT
    items: list = field(default_factory=list)
    events: list = field(default_factory=list)
    tracking_number: str | None = None
    cancel_reason: str | None = None

    # -- consultas
    @property
    def units(self) -> int:
        return sum(item.quantity for item in self.items)  # suma unidades, no renglones

    @property
    def total(self) -> Money:
        amount = sum((x.subtotal.amount for x in self.items), Decimal("0"))
        return Money(amount)

    # -- comandos
    def add_item(self, item: OrderItem) -> None:
        if self.status != OrderStatus.DRAFT:
            raise InvalidOrderTransition(self.status.value, "agregar artículos a")
        if item.unit_price.currency != "MXN":
            raise InvalidOrderData("Solo MXN")
        if self.units + item.quantity > MAX_UNITS:
            raise OrderItemLimitExceeded(self.units + item.quantity)
        self.items.append(item)

    def _record(self, name: str) -> None:
        self.events.append(DomainEvent(name, self.id))

    def _require(self, expected: OrderStatus, action: str) -> None:
        if self.status != expected:
            raise InvalidOrderTransition(self.status.value, action)

    def confirm(self) -> None:
        self._require(OrderStatus.DRAFT, "confirmar")
        if not self.items:
            raise InvalidOrderData("No se puede confirmar un pedido sin artículos")
        if not self.customer.active:
            raise InvalidOrderData("No se puede confirmar: el cliente está inactivo")
        self.status = OrderStatus.CONFIRMED
        self._record("OrderConfirmed")

    def ship(self, tracking_number: str) -> None:
        self._require(OrderStatus.CONFIRMED, "enviar")
        if not tracking_number or not tracking_number.strip():
            raise InvalidOrderData("El envío requiere número de guía")
        self.tracking_number = tracking_number.strip()
        self.status = OrderStatus.SHIPPED
        self._record("OrderShipped")

    def cancel(self, reason: str) -> None:
        self._require(OrderStatus.CONFIRMED, "cancelar")
        if not reason or not reason.strip():
            raise InvalidOrderData("La cancelación requiere un motivo")
        self.cancel_reason = reason.strip()
        self.status = OrderStatus.CANCELLED
        self._record("OrderCancelled")

    def deliver(self) -> None:
        self._require(OrderStatus.SHIPPED, "entregar")
        self.status = OrderStatus.DELIVERED
        self._record("OrderDelivered")

    def return_order(self) -> None:
        self._require(OrderStatus.SHIPPED, "devolver")
        self.status = OrderStatus.RETURNED
        self._record("OrderReturned")
