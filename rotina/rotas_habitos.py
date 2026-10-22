"""Cadastro, registro diário e histórico dos hábitos."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .configuracao import hoje, parse_data
from .modelos import db, Habito
from . import servicos as sv

bp = Blueprint("habitos", __name__, url_prefix="/habitos")


def _voltar(padrao="habitos.lista"):
    destino = request.form.get("next") or request.args.get("next") or ""
    if destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)
    return redirect(url_for(padrao))


def _get(hid):
    h = db.session.get(Habito, hid)
    if not h:
        abort(404)
    return h


def _num(campo):
    bruto = (request.form.get(campo) or "").strip().replace(",", ".")
    if not bruto:
        return None
    try:
        return float(bruto)
    except ValueError:
        return None


@bp.route("/")
def lista():
    ativos = [sv.resumo_habito(h) for h in sv.habitos_ativos()]
    arquivados = Habito.query.filter_by(ativo=False).order_by(Habito.arquivado_em.desc()).all()
    arq = [(h, sv.sequencias(h)) for h in arquivados]
    return render_template("habitos.html", ativos=ativos, arquivados=arq)


@bp.route("/novo", methods=["GET", "POST"])
@bp.route("/<int:hid>/editar", methods=["GET", "POST"])
def form(hid=None):
    h = _get(hid) if hid else None
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()[:80]
        if not nome:
            flash("Dê um nome ao hábito.")
            return render_template("habito_form.html", h=h, tipos=Habito.TIPOS)
        novo = h is None
        if novo:
            h = Habito(criado_em=hoje(), ordem=Habito.query.count())
        h.nome = nome
        tipo = request.form.get("tipo", "sim_nao")
        h.tipo = tipo if tipo in Habito.TIPOS else "sim_nao"
        h.unidade = (request.form.get("unidade") or "").strip()[:20]
        h.direcao = "max" if request.form.get("direcao") == "max" else "min"
        h.meta = _num("meta")
        h.meta_minima = _num("meta_minima")
        h.versao_minima = (request.form.get("versao_minima") or "").strip()[:120]
        freq = request.form.get("frequencia", "diaria")
        h.frequencia = freq if freq in ("diaria", "semanal", "dias") else "diaria"
        try:
            h.vezes_semana = max(1, min(7, int(request.form.get("vezes_semana") or 3)))
        except ValueError:
            h.vezes_semana = 3
        dias = [d for d in request.form.getlist("dias") if d in "0123456" and len(d) == 1]
        h.dias_semana = ",".join(sorted(set(dias)))
        if h.frequencia == "dias" and not h.dias_semana:
            h.frequencia = "diaria"
        h.no_fechamento = bool(request.form.get("no_fechamento"))
        try:
            h.ordem = int(request.form.get("ordem") or h.ordem or 0)
        except ValueError:
            pass
        db.session.add(h)
        db.session.commit()
        flash("Hábito criado." if novo else "Hábito salvo.")
        return redirect(url_for("habitos.lista"))
    return render_template("habito_form.html", h=h, tipos=Habito.TIPOS)


@bp.route("/<int:hid>/registrar", methods=["POST"])
def registrar(hid):
    h = _get(hid)
    d = parse_data(request.form.get("data")) or hoje()
    if d > hoje():
        abort(400)
    if h.tipo == "numero":
        sv.registrar(h, d, valor=_num("valor"))
    elif h.tipo == "sim_nao":
        nivel = request.form.get("nivel") or None
        if nivel not in (None, "minimo", "feito"):
            abort(400)
        sv.registrar(h, d, nivel=nivel)
    return _voltar("hoje.hoje_view")


@bp.route("/<int:hid>/arquivar", methods=["POST"])
def arquivar(hid):
    h = _get(hid)
    h.ativo = False
    h.arquivado_em = hoje()
    db.session.commit()
    flash(f"“{h.nome}” arquivado. O histórico fica guardado.")
    return redirect(url_for("habitos.lista"))


@bp.route("/<int:hid>/reativar", methods=["POST"])
def reativar(hid):
    h = _get(hid)
    h.ativo = True
    h.arquivado_em = None
    db.session.commit()
    flash(f"“{h.nome}” de volta. A melhor sequência continua registrada.")
    return redirect(url_for("habitos.lista"))


@bp.route("/<int:hid>/excluir", methods=["POST"])
def excluir(hid):
    h = _get(hid)
    if h.ativo:
        abort(400)
    db.session.delete(h)
    db.session.commit()
    flash("Hábito excluído com todo o histórico.")
    return redirect(url_for("habitos.lista"))
