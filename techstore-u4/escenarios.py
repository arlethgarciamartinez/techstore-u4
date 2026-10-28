"""Ejecuta los 15 escenarios E01-E15 de datos/escenarios.csv y genera la bitácora.

Uso: python escenarios.py            (imprime tabla)
     python escenarios.py --json     (escribe evidencias/bitacora.json)
"""
import json
import sys
from decimal import Decimal

from app.domain import DomainException, Money, OrderItem
from app.specifications import discount_rate, ten_percent, five_percent
from cargar_csv import load_fixture


def estado(o):
    return o.status.value


def run_case(caso):
    """Devuelve dict con: estado inicial, operación, resultado real, eventos."""
    orders = load_fixture()  # datos frescos para cada caso
    o = orders[caso["pedido_id"]]
    ini = f"{estado(o)} · {o.units} u · ${o.total.amount}"
    cid = caso["caso_id"]
    pasos, resultado, esperado_ok = [], "", True

    def intenta(nombre, fn):
        try:
            fn()
            pasos.append(f"{nombre}: OK")
            return None
        except DomainException as exc:
            pasos.append(f"{nombre}: {type(exc).__name__}")
            return exc

    if caso["accion"] == "evaluar_descuento":
        r = discount_rate(o)
        resultado = f"descuento {int(r * 100)}% (10%={ten_percent.is_satisfied_by(o)}, 5%={five_percent.is_satisfied_by(o)})"
        pasos.append("discount_rate(order)")
    elif cid == "E03" or cid == "E06" or cid == "E07":
        exc = intenta("confirm()", o.confirm)
        resultado = f"rechazo: {exc}" if exc else f"éxito: {estado(o)}"
    elif cid == "E08":
        exc = intenta("add_item(SKU003 x2)", lambda: o.add_item(OrderItem("SKU003", 2, Money(Decimal("120.00")))))
        resultado = f"rechazo: {exc}" if exc else "éxito"
    elif cid == "E11":
        intenta("confirm()", o.confirm)
        exc = intenta("ship('')", lambda: o.ship(""))
        resultado = f"confirm OK; envío rechazado: {exc}" if exc else "envío aceptado"
    elif cid == "E12":
        intenta("confirm() #1", o.confirm)
        exc = intenta("confirm() #2", o.confirm)
        resultado = f"1ª OK; 2ª rechazada: {exc}" if exc else "2ª aceptada"
    elif cid == "E13":
        intenta("confirm()", o.confirm)
        intenta("ship('GUIA-001')", lambda: o.ship("GUIA-001"))
        exc = intenta("cancel('cliente')", lambda: o.cancel("cliente"))
        resultado = f"confirm+ship OK; cancelación rechazada: {exc}" if exc else "cancelación aceptada"
    elif cid in ("E14", "E15"):
        intenta("confirm()", o.confirm)
        intenta("ship('GUIA-001')", lambda: o.ship("GUIA-001"))
        if cid == "E14":
            intenta("return_order()", o.return_order)
        else:
            intenta("deliver()", o.deliver)
        resultado = f"éxito: termina en {estado(o)}"
    return {
        "caso": cid,
        "pedido": o.id,
        "objetivo": caso["objetivo"],
        "estado_inicial": ini,
        "operacion": " → ".join(pasos),
        "resultado": resultado,
        "estado_final": estado(o),
        "eventos": [e.name for e in o.events],
    }


def main():
    import csv

    with open("datos/escenarios.csv", encoding="utf-8-sig", newline="") as f:
        casos = list(csv.DictReader(f))
    filas = [run_case(c) for c in casos]
    if "--json" in sys.argv:
        with open("evidencias/bitacora.json", "w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=1)
    for r in filas:
        print(f"{r['caso']} {r['pedido']} | {r['estado_inicial']} | {r['operacion']} | {r['resultado']} | final={r['estado_final']} eventos={r['eventos']}")


if __name__ == "__main__":
    main()
