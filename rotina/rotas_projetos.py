"""Aba Projetos: lista com números, criação, edição, arquivo e página de cada projeto."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .modelos import db, Projeto, Tarefa
from . import estatisticas as est
from . import graficos

bp = Blueprint("projetos", __name__, url_prefix="/projetos")

CORES = ["#5b8fe0", "#2fae78", "#c0873a", "#8a7fd8", "#d0647a", "#3aa6b9", "#9a9f2e", "#a0a6b5"]


def _get(pid):
    p = db.session.get(Projeto, pid)
    if not p:
        abort(404)
    return p


def _dados_form(p):
    nome = (request.form.get("nome") or "").strip()[:80]
    cor = request.form.get("cor") or p.cor or CORES[0]
    if not (len(cor) == 7 and cor.startswith("#")):
        cor = CORES[0]
    return nome, cor, (request.form.get("descricao") or "").strip()[:1000]


@bp.route("/")
def lista():
    ativos = est.resumo_projetos(False)
    arquivados = est.resumo_projetos(True)
    avulsas = Tarefa.query.filter(Tarefa.projeto_id.is_(None), Tarefa.status != "feito").count()
    sugestao = CORES[len(ativos) % len(CORES)]
    return render_template("projetos.html", ativos=ativos, arquivados=arquivados,
                           avulsas=avulsas, cores=CORES, sugestao=sugestao)


@bp.route("/novo", methods=["POST"])
def novo():
    p = Projeto()
    nome, cor, descricao = _dados_form(p)
    if not nome:
        flash("Dê um nome ao projeto.")
        return redirect(url_for("projetos.lista"))
    p.nome, p.cor, p.descricao = nome, cor, descricao
    db.session.add(p)
    db.session.commit()
    flash(f"Projeto “{p.nome}” criado.")
    return redirect(url_for("projetos.detalhe", pid=p.id))


@bp.route("/<int:pid>")
def detalhe(pid):
    p = _get(pid)
    r = est.resumo_projeto(p)
    abertas = (Tarefa.query.filter(Tarefa.projeto_id == p.id, Tarefa.status != "feito")
               .order_by(Tarefa.prazo.is_(None), Tarefa.prazo, Tarefa.id).all())
    concluidas = (Tarefa.query.filter(Tarefa.projeto_id == p.id, Tarefa.status == "feito")
                  .order_by(Tarefa.concluida_em.desc()).all())
    dias = est.dias_ate_hoje(30)
    serie = est.serie_tarefas(dias, projeto_id=p.id)
    grafico = graficos.barras(
        [d.strftime("%d/%m") for d in dias],
        [{"nome": "concluídas", "cor": "#2fae78", "valores": [x["concluidas"] for x in serie]},
         {"nome": "a fazer", "cor": "#5b8fe0", "valores": [x["a_fazer"] for x in serie]}],
        modo="agrupado", altura=200, titulo=f"Tarefas de {p.nome} por dia",
        dicas=[f'{x["data"].strftime("%d/%m")} · {x["concluidas"]} concluída(s) · {x["a_fazer"]} a fazer'
               for x in serie])
    return render_template("projeto.html", p=p, r=r, abertas=abertas, concluidas=concluidas,
                           grafico=grafico, serie=serie, cores=CORES)


@bp.route("/<int:pid>/editar", methods=["POST"])
def editar(pid):
    p = _get(pid)
    nome, cor, descricao = _dados_form(p)
    if nome:
        p.nome = nome
    p.cor, p.descricao = cor, descricao
    db.session.commit()
    flash("Projeto salvo.")
    return redirect(url_for("projetos.detalhe", pid=p.id))


@bp.route("/<int:pid>/arquivar", methods=["POST"])
def arquivar(pid):
    p = _get(pid)
    p.arquivado = True
    db.session.commit()
    flash(f"“{p.nome}” arquivado. As tarefas continuam guardadas.")
    return redirect(url_for("projetos.lista"))


@bp.route("/<int:pid>/restaurar", methods=["POST"])
def restaurar(pid):
    p = _get(pid)
    p.arquivado = False
    db.session.commit()
    flash(f"“{p.nome}” de volta aos projetos ativos.")
    return redirect(url_for("projetos.lista"))


@bp.route("/<int:pid>/excluir", methods=["POST"])
def excluir(pid):
    p = _get(pid)
    if not p.arquivado:
        abort(400)
    n = Tarefa.query.filter_by(projeto_id=p.id).update({"projeto_id": None})
    db.session.delete(p)
    db.session.commit()
    flash(f"Projeto excluído. {n} tarefa(s) ficaram como avulsas.")
    return redirect(url_for("projetos.lista"))
