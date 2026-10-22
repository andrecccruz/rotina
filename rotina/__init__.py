"""Fábrica do app Flask."""
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, abort, request

from .configuracao import (RAIZ, carregar_config, definir_fuso, data_br, data_curta,
                           data_extenso, duracao, hoje, DIAS_SEMANA)
from .modelos import db, Habito


HABITOS_INICIAIS = [
    dict(nome="Redes sociais", tipo="numero", unidade="min", direcao="max", no_fechamento=True,
         versao_minima="registrar o tempo de tela"),
    dict(nome="Checagens do celular", tipo="numero", unidade="desbloqueios", direcao="max",
         no_fechamento=True, versao_minima="registrar os desbloqueios"),
    dict(nome="Leitura", tipo="numero", unidade="páginas", direcao="min", meta=10, meta_minima=2,
         no_fechamento=True, versao_minima="2 páginas"),
    dict(nome="Concluir a prioridade do dia", tipo="auto_prioridade",
         versao_minima="trabalhar nela com o timer"),
    dict(nome="Estado de flow", tipo="auto_flow", meta=60, meta_minima=25,
         versao_minima="uma sessão focada de 25 min"),
    dict(nome="Ambiente organizado", tipo="sim_nao", no_fechamento=True,
         versao_minima="arrumar a cama"),
    dict(nome="Desacelerar à noite", tipo="sim_nao", frequencia="dias", dias_semana="0,1,2,3,4",
         no_fechamento=True, versao_minima="10 min sem tela antes de dormir"),
    dict(nome="Journaling", tipo="auto_journal", versao_minima="uma linha no fechamento"),
]


def _semear():
    if Habito.query.count():
        return
    for i, dados in enumerate(HABITOS_INICIAIS):
        db.session.add(Habito(ordem=i, criado_em=hoje(), **dados))
    db.session.commit()


# Colunas adicionadas depois da v1: (tabela, coluna, DDL). create_all() não altera tabelas
# que já existem, então bancos antigos recebem a coluna aqui, sem perder dados.
MIGRACOES = [
    ("projeto", "descricao", "TEXT NOT NULL DEFAULT ''"),
]


def _migrar():
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    for tabela, coluna, ddl in MIGRACOES:
        if tabela in insp.get_table_names() and coluna not in {c["name"] for c in insp.get_columns(tabela)}:
            with db.engine.begin() as con:
                con.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {ddl}"))


def criar_app(config_extra=None):
    load_dotenv(os.path.join(RAIZ, ".env"))
    app = Flask(__name__)
    cfg = carregar_config()
    if config_extra:
        cfg.update(config_extra.get("ROTINA", {}))
    definir_fuso(cfg["fuso_horario"])

    pasta_dados = os.path.join(RAIZ, "dados")
    os.makedirs(pasta_dados, exist_ok=True)
    app.config.update(
        ROTINA=cfg,
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(pasta_dados, "rotina.db"),
        SECRET_KEY=os.environ.get("ROTINA_SECRET") or "rotina-local",
        SEMEAR=True,
    )
    if config_extra:
        app.config.update({k: v for k, v in config_extra.items() if k != "ROTINA"})

    if os.environ.get("ROTINA_PROXY") == "1":
        # Atrás de proxy reverso (Docker + túnel): usa o host original (X-Forwarded-Host)
        # na checagem de origem. Só ligar quando houver um proxy na frente.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)

    from .rotas_hoje import bp as bp_hoje
    from .rotas_habitos import bp as bp_habitos
    from .rotas_tarefas import bp as bp_tarefas
    from .rotas_garagem import bp as bp_garagem
    from .rotas_ia import bp as bp_ia
    from .rotas_calendario import bp as bp_cal
    from .rotas_projetos import bp as bp_proj
    from .rotas_evolucao import bp as bp_evo
    for bp in (bp_hoje, bp_habitos, bp_tarefas, bp_garagem, bp_ia, bp_cal, bp_proj, bp_evo):
        app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        _migrar()
        if app.config["SEMEAR"]:
            _semear()
        from .servicos import data_inicio_uso
        data_inicio_uso()

    @app.before_request
    def _mesma_origem():
        # App local sem login: recusa POST vindo de outro site aberto no navegador.
        if request.method == "POST":
            origem = request.headers.get("Origin") or request.headers.get("Referer")
            if origem and urlparse(origem).netloc != request.host:
                abort(403)

    @app.context_processor
    def _globais():
        from .servicos import sessao_ativa
        s = sessao_ativa()
        return {
            "nome_app": cfg["nome_app"],
            "timer": s,
            "ia_ativa": bool(cfg["ia"].get("ativa")),
            "hoje_data": hoje(),
            "DIAS_SEMANA": DIAS_SEMANA,
        }

    app.jinja_env.filters["data_br"] = data_br
    app.jinja_env.filters["data_curta"] = data_curta
    app.jinja_env.filters["data_extenso"] = data_extenso
    app.jinja_env.filters["duracao"] = duracao
    app.jinja_env.filters["num"] = lambda v: "" if v is None else (
        str(int(v)) if float(v).is_integer() else f"{v:.1f}".replace(".", ","))
    return app
