"""Rotas da IA (somente leitura). Respondem JSON: {ok, texto, cache, criada_em} ou {ok: false, erro}.

Antes de chamar o provedor, sempre olha o cache (tabela resposta_ia): se o contexto
enviado seria idêntico, devolve a resposta guardada e não gasta tokens."""
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, url_for

from .modelos import db, RespostaIA, Tarefa
from . import ia

bp = Blueprint("ia", __name__, url_prefix="/ia")


def _cfg():
    return current_app.config["ROTINA"]["ia"]


def _json(res):
    return jsonify(ok=True, texto=res["texto"], cache=res["cache"],
                   criada_em=res["criada_em"].strftime("%d/%m %H:%M"))


def _responder(funcao, pacote):
    mensagens, chave = pacote
    forcar = bool((request.get_json(silent=True) or {}).get("refazer") or request.args.get("refazer"))
    try:
        return _json(ia.responder(_cfg(), funcao, mensagens, chave, forcar=forcar))
    except ia.ErroIA as e:
        return jsonify(ok=False, erro=str(e)), 200


def _modo_e_pergunta():
    dados = request.get_json(silent=True) or request.values
    modo = dados.get("modo", "primeiro")
    if modo not in ("primeiro", "semana", "livre"):
        modo = "primeiro"
    pergunta = (dados.get("pergunta") or "").strip()
    if modo == "livre" and not pergunta:
        modo = "primeiro"
    return modo, pergunta


@bp.route("/explicar/<int:tid>", methods=["POST"])
def explicar(tid):
    t = db.session.get(Tarefa, tid) or abort(404)
    return _responder("explicar", ia.mensagens_explicar(t))


@bp.route("/perguntar", methods=["POST"])
def perguntar():
    modo, pergunta = _modo_e_pergunta()
    return _responder(modo, ia.mensagens_painel(modo, pergunta, _cfg()))


@bp.route("/memoria")
def memoria():
    """Só consulta o cache (nunca chama a IA). Usado ao abrir a tela Hoje."""
    if not _cfg().get("ativa"):
        return jsonify(ok=False)
    modo, pergunta = _modo_e_pergunta()
    _, chave = ia.mensagens_painel(modo, pergunta, _cfg())
    r = ia.consultar_cache(_cfg(), chave)
    if not r:
        return jsonify(ok=False)
    r.usos += 1
    db.session.commit()
    return jsonify(ok=True, texto=r.texto, cache=True, criada_em=r.criada_em.strftime("%d/%m %H:%M"))


@bp.route("/testar", methods=["POST"])
def testar():
    try:
        texto, _ = ia.chamar(_cfg(), [{"role": "user", "content": "Responda apenas: ok"}], "teste")
        return jsonify(ok=True, texto=texto, cache=False, criada_em="agora")
    except ia.ErroIA as e:
        return jsonify(ok=False, erro=str(e))


@bp.route("/limpar-cache", methods=["POST"])
def limpar_cache():
    n = RespostaIA.query.delete()
    db.session.commit()
    flash(f"Memória da IA limpa ({n} resposta{'s' if n != 1 else ''}).")
    return redirect(url_for("hoje.ajustes"))
