"""Calendário mensal: hábitos, prazos, prioridades e tempo, dia a dia."""
from datetime import date, timedelta

from flask import Blueprint, render_template, request

from .configuracao import hoje, parse_data, MESES_LONGOS
from . import servicos as sv

bp = Blueprint("calendario", __name__)


def _mes(texto):
    try:
        ano, mes = (int(x) for x in (texto or "").split("-")[:2])
        return date(ano, mes, 1)
    except (ValueError, TypeError):
        return None


@bp.route("/calendario")
def mes():
    dia = parse_data(request.args.get("dia"))
    base = _mes(request.args.get("mes")) or (dia.replace(day=1) if dia else hoje().replace(day=1))
    if not dia or (dia.year, dia.month) != (base.year, base.month):
        dia = hoje() if (hoje().year, hoje().month) == (base.year, base.month) else None
    anterior = (base.replace(day=1) - timedelta(days=1)).replace(day=1)
    seguinte = (base.replace(day=28) + timedelta(days=4)).replace(day=1)
    semanas = sv.calendario_mes(base.year, base.month)
    dias_mes = [c for s in semanas for c in s if c["no_mes"] and not c["futuro"] and c["previstos"]]
    total_prev = sum(c["previstos"] for c in dias_mes)
    resumo = {
        "taxa": round(100 * sum(c["cumpridos"] for c in dias_mes) / total_prev) if total_prev else None,
        "focados": sum(c["focados"] for s in semanas for c in s if c["no_mes"]),
        "concluidas": sum(c["concluidas"] for s in semanas for c in s if c["no_mes"]),
        "journal": sum(1 for s in semanas for c in s if c["no_mes"] and c["journal"]),
    }
    return render_template(
        "calendario.html", semanas=semanas, base=base, dia=dia,
        detalhe=sv.detalhe_dia(dia) if dia else None,
        titulo_mes=f"{MESES_LONGOS[base.month - 1]} {base.year}",
        anterior=anterior, seguinte=seguinte, resumo=resumo,
    )
