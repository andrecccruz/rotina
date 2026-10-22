"""Tela Hoje, Fechamento do dia e Ajustes."""
import os
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .configuracao import agora, hoje, parse_data
from .modelos import db, Fechamento, Habito, Tarefa
from . import servicos as sv

bp = Blueprint("hoje", __name__)


def _tarefas_abertas():
    return (Tarefa.query.filter(Tarefa.status != "feito")
            .order_by(Tarefa.prazo.is_(None), Tarefa.prazo, Tarefa.id).all())


@bp.route("/")
def hoje_view():
    d = hoje()
    resumos = [sv.resumo_habito(h, semanas_grade=1) for h in sv.habitos_ativos()]
    resumos = [r for r in resumos if r["agendado_hoje"]]
    abertas = _tarefas_abertas()
    prioridade = Tarefa.query.filter_by(prioritaria_em=d).first()
    atrasadas = [t for t in abertas if t.prazo and t.prazo < d]
    vencem = [t for t in abertas if t.prazo == d]
    ids = {t.id for t in atrasadas + vencem} | ({prioridade.id} if prioridade else set())
    fazendo = [t for t in abertas if t.status == "fazendo" and t.id not in ids]
    inicio_dia = datetime.combine(d, datetime.min.time())
    concluidas = Tarefa.query.filter(Tarefa.concluida_em >= inicio_dia).count()
    cumpridos = sum(1 for r in resumos if r["nivel_hoje"])
    return render_template(
        "hoje.html", resumos=resumos, prioridade=prioridade, atrasadas=atrasadas,
        vencem=vencem, fazendo=fazendo, abertas=abertas, concluidas=concluidas,
        minutos=sv.minutos_hoje(), cumpridos=cumpridos,
    )


@bp.route("/fechamento", methods=["GET", "POST"])
def fechamento():
    d = parse_data(request.values.get("data")) or hoje()
    if d > hoje():
        d = hoje()
    amanha = d + timedelta(days=1)
    habitos = [h for h in sv.habitos_ativos() if h.no_fechamento and sv.agendado(h, d)]
    fech = Fechamento.query.filter_by(data=d).first()

    if request.method == "POST":
        for h in habitos:
            if h.tipo == "numero":
                bruto = request.form.get(f"valor_{h.id}", "").strip().replace(",", ".")
                try:
                    valor = float(bruto) if bruto else None
                except ValueError:
                    valor = None
                sv.registrar(h, d, valor=valor)
            elif h.tipo == "sim_nao":
                sv.registrar(h, d, nivel=request.form.get(f"nivel_{h.id}") or None)
        fech = fech or Fechamento(data=d)
        fech.journaling = request.form.get("journaling", "").strip()
        fech.salvo_em = agora()
        db.session.add(fech)

        tid = request.form.get("prioridade_amanha", "")
        for t in Tarefa.query.filter_by(prioritaria_em=amanha).all():
            t.prioritaria_em = None
        if tid.isdigit():
            t = db.session.get(Tarefa, int(tid))
            if t:
                t.prioritaria_em = amanha
                passo = request.form.get("proximo_passo", "").strip()
                if passo:
                    t.proximo_passo = passo[:300]
        db.session.commit()
        flash("Dia fechado. Até amanhã.")
        return redirect(url_for("hoje.fechamento", data=d.isoformat()))

    valores = {}
    for h in habitos:
        r = next((x for x in h.registros if x.data == d), None)
        valores[h.id] = r
    automaticos = []
    for h in sv.habitos_ativos():
        if h.automatico and sv.agendado(h, d):
            automaticos.append((h, sv.niveis_intervalo(h, d, d).get(d)))
    prioridade_amanha = Tarefa.query.filter_by(prioritaria_em=amanha).first()
    return render_template(
        "fechamento.html", d=d, amanha=amanha, habitos=habitos, valores=valores,
        fech=fech, automaticos=automaticos, abertas=_tarefas_abertas(),
        prioridade_amanha=prioridade_amanha, ontem=d - timedelta(days=1),
    )


@bp.route("/ajustes")
def ajustes():
    cfg = current_app.config["ROTINA"]
    ia = dict(cfg["ia"])
    chave = bool(os.environ.get("AZURE_OPENAI_API_KEY"))
    inicio = sv.data_inicio_uso()
    liberacao = inicio + timedelta(days=int(cfg.get("dias_congelamento_funcionalidades", 14)))
    from .ia import estatisticas_cache
    return render_template("ajustes.html", cfg=cfg, ia=ia, chave=chave, cache=estatisticas_cache(),
                           inicio=inicio, liberacao=liberacao,
                           total_habitos=Habito.query.count())
