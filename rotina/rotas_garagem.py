"""Garagem de ideias: capturar sem trocar de tarefa."""
from datetime import timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .configuracao import hoje
from .modelos import db, Ideia, Projeto, Tarefa
from . import servicos as sv

bp = Blueprint("garagem", __name__, url_prefix="/garagem")


@bp.route("/")
def lista():
    etiqueta = request.args.get("etiqueta", "")
    q = Ideia.query.filter_by(situacao="aberta")
    if etiqueta in ("geral", "app"):
        q = q.filter_by(etiqueta=etiqueta)
    ideias = q.order_by(Ideia.criada_em.desc()).all()
    dias = int(current_app.config["ROTINA"].get("dias_congelamento_funcionalidades", 14))
    liberacao = sv.data_inicio_uso() + timedelta(days=dias)
    congelado = hoje() < liberacao
    total_app = Ideia.query.filter_by(situacao="aberta", etiqueta="app").count()
    projetos = Projeto.query.filter_by(arquivado=False).order_by(Projeto.nome).all()
    return render_template("garagem.html", ideias=ideias, etiqueta=etiqueta,
                           liberacao=liberacao, congelado=congelado,
                           faltam=(liberacao - hoje()).days, total_app=total_app,
                           projetos=projetos)


@bp.route("/capturar", methods=["POST"])
def capturar():
    texto = (request.form.get("texto") or "").strip()[:500]
    etiqueta = "app" if request.form.get("etiqueta") == "app" else "geral"
    if texto.lower().startswith("app:"):
        etiqueta, texto = "app", texto[4:].strip()
    if texto:
        db.session.add(Ideia(texto=texto, etiqueta=etiqueta))
        db.session.commit()
        flash("Ideia estacionada na garagem. Pode voltar ao que estava fazendo.")
    destino = request.form.get("next") or ""
    if destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)
    return redirect(url_for("garagem.lista"))


@bp.route("/<int:iid>/promover", methods=["POST"])
def promover(iid):
    i = db.session.get(Ideia, iid) or abort(404)
    pid = request.form.get("projeto_id", "")
    t = Tarefa(titulo=i.texto[:200], descricao=i.texto if len(i.texto) > 200 else "",
               projeto_id=int(pid) if pid.isdigit() else None)
    db.session.add(t)
    db.session.flush()
    i.situacao, i.tarefa_id = "promovida", t.id
    db.session.commit()
    flash("Ideia virou tarefa.")
    return redirect(url_for("tarefas.form", tid=t.id))


@bp.route("/<int:iid>/descartar", methods=["POST"])
def descartar(iid):
    i = db.session.get(Ideia, iid) or abort(404)
    i.situacao = "descartada"
    db.session.commit()
    return redirect(request.referrer or url_for("garagem.lista"))
