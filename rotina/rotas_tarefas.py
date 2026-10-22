"""Tarefas, projetos e timer único."""
from datetime import timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from .configuracao import hoje, parse_data
from .modelos import db, Projeto, Tarefa
from . import servicos as sv

bp = Blueprint("tarefas", __name__)


def _voltar(padrao="tarefas.lista"):
    destino = request.form.get("next") or request.args.get("next") or ""
    if destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)
    return redirect(url_for(padrao))


def _get(tid):
    t = db.session.get(Tarefa, tid)
    if not t:
        abort(404)
    return t


def _projetos():
    return Projeto.query.filter_by(arquivado=False).order_by(Projeto.nome).all()


@bp.route("/tarefas")
def lista():
    filtro = request.args.get("status", "abertas")
    if filtro not in ("abertas", "feito", "todas"):
        filtro = "abertas"
    projeto = request.args.get("projeto", "")
    q = Tarefa.query
    base = Tarefa.query
    if projeto == "avulso":
        base = base.filter(Tarefa.projeto_id.is_(None))
    elif projeto.isdigit():
        base = base.filter(Tarefa.projeto_id == int(projeto))
    contagens = {"abertas": base.filter(Tarefa.status != "feito").count(),
                 "feito": base.filter(Tarefa.status == "feito").count()}
    contagens["todas"] = contagens["abertas"] + contagens["feito"]
    if filtro == "abertas":
        q = q.filter(Tarefa.status != "feito")
    elif filtro == "feito":
        q = q.filter(Tarefa.status == "feito")
    if projeto == "avulso":
        q = q.filter(Tarefa.projeto_id.is_(None))
    elif projeto.isdigit():
        q = q.filter(Tarefa.projeto_id == int(projeto))
    if filtro == "feito":
        tarefas = q.order_by(Tarefa.concluida_em.desc()).limit(200).all()
    else:
        tarefas = q.order_by(Tarefa.prazo.is_(None), Tarefa.prazo, Tarefa.id.desc()).all()
    return render_template("tarefas.html", tarefas=tarefas, projetos=_projetos(),
                           filtro=filtro, projeto=projeto, contagens=contagens)


@bp.route("/tarefas/nova", methods=["GET", "POST"])
@bp.route("/tarefas/<int:tid>/editar", methods=["GET", "POST"])
def form(tid=None):
    t = _get(tid) if tid else None
    if request.method == "POST":
        titulo = (request.form.get("titulo") or "").strip()[:200]
        if not titulo:
            flash("A tarefa precisa de um título.")
            return redirect(request.url)
        novo = t is None
        t = t or Tarefa()
        t.titulo = titulo
        t.descricao = (request.form.get("descricao") or "").strip()
        pid = request.form.get("projeto_id", "")
        t.projeto_id = int(pid) if pid.isdigit() and db.session.get(Projeto, int(pid)) else None
        t.prazo = parse_data(request.form.get("prazo"))
        t.proximo_passo = (request.form.get("proximo_passo") or "").strip()[:300]
        status = request.form.get("status")
        if status in Tarefa.STATUS and not novo:
            if status == "feito" and t.status != "feito":
                sv.concluir_tarefa(t)
            elif status != "feito" and t.status == "feito":
                sv.reabrir_tarefa(t)
            t.status = status
        db.session.add(t)
        db.session.commit()
        flash("Tarefa criada." if novo else "Tarefa salva.")
        return _voltar()
    return render_template("tarefa_form.html", t=t, projetos=_projetos())


@bp.route("/tarefas/rapida", methods=["POST"])
def rapida():
    titulo = (request.form.get("titulo") or "").strip()[:200]
    if titulo:
        pid = request.form.get("projeto_id", "")
        t = Tarefa(titulo=titulo, prazo=parse_data(request.form.get("prazo")),
                   projeto_id=int(pid) if pid.isdigit() else None)
        db.session.add(t)
        db.session.commit()
    return _voltar()


@bp.route("/tarefas/<int:tid>/concluir", methods=["POST"])
def concluir(tid):
    sv.concluir_tarefa(_get(tid))
    return _voltar()


@bp.route("/tarefas/<int:tid>/reabrir", methods=["POST"])
def reabrir(tid):
    sv.reabrir_tarefa(_get(tid))
    return _voltar()


@bp.route("/tarefas/<int:tid>/excluir", methods=["POST"])
def excluir(tid):
    t = _get(tid)
    if sv.sessao_ativa() and sv.sessao_ativa().tarefa_id == t.id:
        sv.parar_timer()
    db.session.delete(t)
    db.session.commit()
    flash("Tarefa excluída.")
    return redirect(url_for("tarefas.lista"))


@bp.route("/tarefas/prioridade", methods=["POST"])
@bp.route("/tarefas/<int:tid>/prioridade", methods=["POST"])
def prioridade(tid=None):
    if tid is None:
        bruto = request.form.get("tid", "")
        if not bruto.isdigit():
            abort(400)
        tid = int(bruto)
    t = _get(tid)
    dia = request.form.get("dia", "hoje")
    if dia == "limpar":
        t.prioritaria_em = None
    else:
        alvo = hoje() if dia == "hoje" else hoje() + timedelta(days=1)
        for outra in Tarefa.query.filter_by(prioritaria_em=alvo).all():
            outra.prioritaria_em = None
        t.prioritaria_em = alvo
    db.session.commit()
    return _voltar()


# ---------------------------------------------------------------- timer

def _estado():
    s = sv.sessao_ativa()
    if not s:
        return {"ativo": False}
    return {"ativo": True, "tarefa_id": s.tarefa_id, "tarefa": s.tarefa.titulo,
            "segundos": s.segundos}


@bp.route("/timer/estado")
def timer_estado():
    return jsonify(_estado())


@bp.route("/timer/iniciar/<int:tid>", methods=["POST"])
def timer_iniciar(tid):
    t = _get(tid)
    if t.status == "feito":
        flash("Reabra a tarefa antes de iniciar o timer.")
        return _voltar()
    anterior = sv.sessao_ativa()
    if anterior and anterior.tarefa_id != t.id:
        flash(f"Timer de “{anterior.tarefa.titulo}” pausado. Uma coisa por vez.")
    sv.iniciar_timer(t)
    return _voltar("hoje.hoje_view")


@bp.route("/timer/parar", methods=["POST"])
def timer_parar():
    focada = request.form.get("focada")
    sv.parar_timer(focada={"sim": True, "nao": False}.get(focada),
                   proximo_passo=request.form.get("proximo_passo"))
    return _voltar("hoje.hoje_view")
