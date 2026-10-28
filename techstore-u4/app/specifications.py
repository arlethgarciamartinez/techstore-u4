"""Specification Pattern: reglas de elegibilidad combinables con & (AND), | (OR) y ~ (NOT).

Una Specification solo EVALÚA (verdadero/falso); nunca modifica el pedido.
"""
from decimal import Decimal

from app.domain import Money, Order


class Specification:
    def is_satisfied_by(self, order: Order) -> bool:
        raise NotImplementedError

    def __and__(self, other):
        return AndSpec(self, other)

    def __or__(self, other):
        return OrSpec(self, other)

    def __invert__(self):
        return NotSpec(self)


class AndSpec(Specification):
    def __init__(self, left, right):
        self.left, self.right = left, right

    def is_satisfied_by(self, order):
        return self.left.is_satisfied_by(order) and self.right.is_satisfied_by(order)


class OrSpec(Specification):
    def __init__(self, left, right):
        self.left, self.right = left, right

    def is_satisfied_by(self, order):
        return self.left.is_satisfied_by(order) or self.right.is_satisfied_by(order)


class NotSpec(Specification):
    def __init__(self, inner):
        self.inner = inner

    def is_satisfied_by(self, order):
        return not self.inner.is_satisfied_by(order)


# ----------------------------------------------------------- reglas simples
class MinimumAmountSpec(Specification):
    """Total ESTRICTAMENTE mayor al umbral (>, no >=)."""

    def __init__(self, threshold: Decimal):
        self.threshold = Money(threshold)

    def is_satisfied_by(self, order):
        return order.total.amount > self.threshold.amount


class VIPCustomerSpec(Specification):
    def is_satisfied_by(self, order):
        return order.customer.is_vip


class MinimumUnitsSpec(Specification):
    """Al menos N unidades (>=)."""

    def __init__(self, minimum: int):
        self.minimum = minimum

    def is_satisfied_by(self, order):
        return order.units >= self.minimum


class ActivePromotionSpec(Specification):
    def is_satisfied_by(self, order):
        return order.has_promotion


# --------------------------------------------------------- reglas compuestas
# 10 %: VIP AND total > 500 AND unidades >= 4 AND NOT promoción
ten_percent = (
    MinimumAmountSpec(Decimal("500"))
    & VIPCustomerSpec()
    & MinimumUnitsSpec(4)
    & ~ActivePromotionSpec()
)
# 5 %: total > 5000 AND NOT promoción
five_percent = MinimumAmountSpec(Decimal("5000")) & ~ActivePromotionSpec()
# Cualquiera de las dos da derecho a descuento (OR)
any_discount = ten_percent | five_percent


def discount_rate(order: Order) -> Decimal:
    """Aplica la prioridad: si cumple ambas, gana el 10 %."""
    if ten_percent.is_satisfied_by(order):
        return Decimal("0.10")
    if five_percent.is_satisfied_by(order):
        return Decimal("0.05")
    return Decimal("0")


def discounted_total(order: Order) -> Money:
    """Calcula el total con descuento sin modificar el pedido."""
    rate = discount_rate(order)
    return Money((order.total.amount * (Decimal("1") - rate)).quantize(Decimal("0.01")))
