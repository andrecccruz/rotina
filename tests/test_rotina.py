import json
from datetime import timedelta, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from rotina import criar_app
from rotina.configuracao import hoje, agora
from rotina.modelos import db, Habito, Registro, Tarefa, SessaoTimer, Ideia, Fechamento
from rotina import servicos as sv


@pytest.fixture
def app(tmp_path, monkeypatch):
    # o log da IA vai para a pasta temporária, nunca para dados/ do usuário
    (tmp_path / "dados").mkdir()
    monkeypatch.setattr("rotina.ia.RAIZ", str(tmp_path))
    app = criar_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db",
                     "SEMEAR": False, "TESTING": True})
    with app.app_context():
        yield app


@pytest.fixture
def cli(app):
    return app.test_client()


def novo_habito(dias_atras=20, **kw):
    dados = dict(nome="H", tipo="sim_nao", criado_em=hoje() - timedelta(days=dias_atras))
    dados.update(kw)
    h = Habito(**dados)
    db.session.add(h)
    db.session.commit()
    return h


def marcar(h, dias_atras, nivel="feito", valor=None):
    db.session.add(Registro(habito_id=h.id, data=hoje() - timedelta(days=dias_atras),
                            nivel=nivel, valor=valor))
    db.session.commit()


# ---------------------------------------------------------------- sequências

def test_sequencia_diaria_e_hoje_nao_quebra(app):
    h = novo_habito()
    for d in (10, 9, 8, 7, 6):      # 5 seguidos
        marcar(h, d)
    for d in (3, 2, 1):             # quebra no 5 e 4, depois 3 seguidos; hoje pendente
        marcar(h, d, "minimo" if d == 2 else "feito")
    atual, melhor, un = sv.sequencias(h)
    assert (atual, melhor, un) == (3, 5, "dias")
    marcar(h, 0)
    assert sv.sequencias(h)[0] == 4


def test_dias_especificos_ignora_dias_livres(app):
    d0 = hoje()
    # agenda só o dia da semana de hoje e o de 2 dias atrás
    dias = sorted({d0.weekday(), (d0 - timedelta(days=2)).weekday()})
    h = novo_habito(dias_atras=2, frequencia="dias", dias_semana=",".join(map(str, dias)))
    marcar(h, 2)
    marcar(h, 0)
    assert sv.sequencias(h)[0] == 2  # o dia 1 (não previsto) não quebra


def test_semanal(app):
    h = novo_habito(dias_atras=30, frequencia="semanal", vezes_semana=2)
    seg = hoje() - timedelta(days=hoje().weekday())
    for semanas in (1, 2):
        base = seg - timedelta(weeks=semanas)
        for i in (0, 2):
            db.session.add(Registro(habito_id=h.id, data=base + timedelta(days=i), nivel="feito"))
    db.session.commit()
    atual, melhor, un = sv.sequencias(h)
    assert un == "semanas" and atual == 2 and melhor == 2


def test_nivel_por_valor():
    h = Habito(tipo="numero", direcao="max", meta=None)
    assert sv.nivel_por_valor(h, 120) == "feito"          # fase de medição
    h.meta, h.meta_minima = 30, 60
    assert sv.nivel_por_valor(h, 25) == "feito"
    assert sv.nivel_por_valor(h, 45) == "minimo"
    assert sv.nivel_por_valor(h, 90) is None
    h2 = Habito(tipo="numero", direcao="min", meta=10, meta_minima=2)
    assert sv.nivel_por_valor(h2, 12) == "feito"
    assert sv.nivel_por_valor(h2, 2) == "minimo"
    assert sv.nivel_por_valor(h2, 1) is None


def test_grade_tem_12_semanas(app):
    h = novo_habito(dias_atras=3)
    marcar(h, 1)
    g = sv.grade(h)
    assert len(g) == 12 and all(len(s) == 7 for s in g)
    estados = {c["data"]: c["estado"] for s in g for c in s}
    assert estados[hoje() - timedelta(days=1)] == "feito"
    assert estados[hoje() - timedelta(days=2)] == "falhou"
    assert estados[hoje()] == "pendente"
    assert estados[hoje() - timedelta(days=10)] == "antes"


# ---------------------------------------------------------------- timer

def test_timer_unico(app):
    a, b = Tarefa(titulo="A"), Tarefa(titulo="B")
    db.session.add_all([a, b])
    db.session.commit()
    sv.iniciar_timer(a)
    sv.iniciar_timer(b)
    ativas = SessaoTimer.query.filter_by(ativa=True).all()
    assert len(ativas) == 1 and ativas[0].tarefa_id == b.id
    assert SessaoTimer.query.filter_by(tarefa_id=a.id).one().fim is not None
    assert a.status == "fazendo"


def test_banco_impede_dois_timers(app):
    t = Tarefa(titulo="A")
    db.session.add(t)
    db.session.commit()
    db.session.add_all([SessaoTimer(tarefa_id=t.id, inicio=agora(), ativa=True),
                        SessaoTimer(tarefa_id=t.id, inicio=agora(), ativa=True)])
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_parar_grava_proximo_passo_e_flow(app, cli):
    h = novo_habito(dias_atras=1, tipo="auto_flow", meta=60, meta_minima=25)
    t = Tarefa(titulo="Estudar redes")
    db.session.add(t)
    db.session.commit()
    s = sv.iniciar_timer(t)
    s.inicio = agora() - timedelta(minutes=30)
    db.session.commit()
    r = cli.post("/timer/parar", data={"focada": "sim", "proximo_passo": "resolver questão 4"})
    assert r.status_code == 302
    db.session.refresh(t)
    assert t.proximo_passo == "resolver questão 4"
    assert sv.niveis_intervalo(h, hoje(), hoje()).get(hoje()) == "minimo"


def test_prioridade_automatica(app, cli):
    h = novo_habito(dias_atras=1, tipo="auto_prioridade")
    t = Tarefa(titulo="Entregar relatório")
    db.session.add(t)
    db.session.commit()
    cli.post("/tarefas/prioridade", data={"tid": t.id, "dia": "hoje"})
    assert sv.niveis_intervalo(h, hoje(), hoje()) == {}
    cli.post(f"/tarefas/{t.id}/concluir")
    assert sv.niveis_intervalo(h, hoje(), hoje())[hoje()] == "feito"


# ---------------------------------------------------------------- telas

def test_fechamento(app, cli):
    redes = novo_habito(nome="Redes", tipo="numero", unidade="min", direcao="max", no_fechamento=True)
    amb = novo_habito(nome="Ambiente", no_fechamento=True)
    jour = novo_habito(nome="Journaling", tipo="auto_journal")
    t = Tarefa(titulo="Amanhã")
    db.session.add(t)
    db.session.commit()
    r = cli.post("/fechamento", data={
        f"valor_{redes.id}": "45", f"nivel_{amb.id}": "minimo",
        "journaling": "Dia ok.", "prioridade_amanha": str(t.id), "proximo_passo": "abrir o doc"})
    assert r.status_code == 302
    assert Registro.query.filter_by(habito_id=redes.id).one().valor == 45
    assert Registro.query.filter_by(habito_id=amb.id).one().nivel == "minimo"
    assert sv.niveis_intervalo(jour, hoje(), hoje())[hoje()] == "feito"
    db.session.refresh(t)
    assert t.prioritaria_em == hoje() + timedelta(days=1) and t.proximo_passo == "abrir o doc"
    assert cli.get("/fechamento").status_code == 200


def test_registrar_toggle(app, cli):
    h = novo_habito()
    cli.post(f"/habitos/{h.id}/registrar", data={"nivel": "feito"})
    assert Registro.query.filter_by(habito_id=h.id).one().nivel == "feito"
    cli.post(f"/habitos/{h.id}/registrar", data={"nivel": ""})
    assert Registro.query.filter_by(habito_id=h.id).count() == 0


def test_garagem(app, cli):
    cli.post("/garagem/capturar", data={"texto": "app: modo escuro alternativo"})
    i = Ideia.query.one()
    assert i.etiqueta == "app" and i.texto == "modo escuro alternativo"
    r = cli.post(f"/garagem/{i.id}/promover", data={})
    assert r.status_code == 302 and Tarefa.query.one().titulo == "modo escuro alternativo"


def test_arquivar_reativar(app, cli):
    h = novo_habito()
    marcar(h, 1)
    cli.post(f"/habitos/{h.id}/arquivar")
    assert not db.session.get(Habito, h.id).ativo
    cli.post(f"/habitos/{h.id}/reativar")
    assert db.session.get(Habito, h.id).ativo
    assert Registro.query.filter_by(habito_id=h.id).count() == 1


def test_post_de_outra_origem_bloqueado(app, cli):
    r = cli.post("/garagem/capturar", data={"texto": "x"}, headers={"Origin": "http://mal.com"})
    assert r.status_code == 403


def test_origem_atras_de_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("ROTINA_PROXY", "1")
    monkeypatch.setattr("rotina.ia.RAIZ", str(tmp_path))
    app = criar_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/p.db",
                     "SEMEAR": False, "TESTING": True})
    cli = app.test_client()
    proxy = {"Host": "rotina:5001", "X-Forwarded-Host": "rotina.exemplo.com"}
    r = cli.post("/garagem/capturar", data={"texto": "x"},
                 headers={**proxy, "Origin": "https://rotina.exemplo.com"})
    assert r.status_code == 302
    r = cli.post("/garagem/capturar", data={"texto": "x"},
                 headers={**proxy, "Origin": "http://mal.com"})
    assert r.status_code == 403


def test_todas_as_telas(app, cli):
    from rotina import HABITOS_INICIAIS, _semear
    _semear()
    t = Tarefa(titulo="T", prazo=hoje() - timedelta(days=1))
    db.session.add(t)
    db.session.commit()
    sv.iniciar_timer(t)
    for url in ["/", "/habitos/", "/habitos/novo", "/tarefas", "/tarefas?status=feito",
                "/tarefas/nova", f"/tarefas/{t.id}/editar", "/garagem/", "/fechamento", "/ajustes"]:
        r = cli.get(url)
        assert r.status_code == 200, url
    assert Habito.query.count() == len(HABITOS_INICIAIS)


# ---------------------------------------------------------------- IA

def test_ia_desligada(app, cli):
    j = cli.post("/ia/perguntar", json={"modo": "primeiro"}).get_json()
    assert j["ok"] is False and "desligada" in j["erro"]


def test_ia_azure(app, cli, monkeypatch):
    cfg = app.config["ROTINA"]["ia"]
    cfg.update(ativa=True, endpoint="https://x.openai.azure.com/", deployment="dep",
               api_version="2024-10-21")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "segredo-123")
    chamadas = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "**Agora**\n- faça X"}}], "usage": {"total_tokens": 5}}

    def falso_post(url, headers=None, json=None, timeout=None):
        chamadas.update(url=url, headers=headers, corpo=json)
        return Resp()

    monkeypatch.setattr("rotina.ia.requests.post", falso_post)
    t = Tarefa(titulo="Configurar VPN", prazo=hoje())
    db.session.add(t)
    db.session.commit()
    j = cli.post(f"/ia/explicar/{t.id}").get_json()
    assert j["ok"] and "faça X" in j["texto"] and "segredo" not in json_dump(j)
    assert chamadas["url"] == ("https://x.openai.azure.com/openai/deployments/dep/chat/completions"
                               "?api-version=2024-10-21")
    assert chamadas["headers"]["api-key"] == "segredo-123"
    assert "Configurar VPN" in chamadas["corpo"]["messages"][1]["content"]
    for modo in ("primeiro", "semana"):
        assert cli.post("/ia/perguntar", json={"modo": modo}).get_json()["ok"]


def test_ia_semana_sem_journaling_por_padrao(app):
    from rotina import ia
    db.session.add(Fechamento(data=hoje(), journaling="segredo pessoal"))
    db.session.commit()
    assert "segredo pessoal" not in ia.contexto_semana(False)
    assert "segredo pessoal" in ia.contexto_semana(True)


def json_dump(x):
    return json.dumps(x)


# ---------------------------------------------------------------- cache da IA e calendário

def _ia_falsa(app, monkeypatch):
    app.config["ROTINA"]["ia"].update(ativa=True, endpoint="https://x.openai.azure.com",
                                      deployment="dep", cache=True, cache_dias=30)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    chamadas = []

    class Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": f"resposta {len(chamadas)}"}}],
                    "usage": {"total_tokens": 500}}

    def falso_post(url, headers=None, json=None, timeout=None):
        chamadas.append(json)
        return Resp()

    monkeypatch.setattr("rotina.ia.requests.post", falso_post)
    return chamadas


def test_cache_nao_gasta_tokens_ao_reabrir(app, cli, monkeypatch):
    chamadas = _ia_falsa(app, monkeypatch)
    t = Tarefa(titulo="Estudar sub-redes")
    db.session.add(t)
    db.session.commit()
    j1 = cli.post(f"/ia/explicar/{t.id}").get_json()
    j2 = cli.post(f"/ia/explicar/{t.id}").get_json()
    assert len(chamadas) == 1 and j1["cache"] is False and j2["cache"] is True
    assert j1["texto"] == j2["texto"]
    # refazer força nova chamada
    cli.post(f"/ia/explicar/{t.id}", json={"refazer": True})
    assert len(chamadas) == 2
    # mudar a tarefa muda a chave
    t.descricao = "cálculo de máscara /26"
    db.session.commit()
    cli.post(f"/ia/explicar/{t.id}")
    assert len(chamadas) == 3


def test_cache_painel_invalida_quando_contexto_muda(app, cli, monkeypatch):
    chamadas = _ia_falsa(app, monkeypatch)
    assert cli.get("/ia/memoria?modo=primeiro").get_json()["ok"] is False
    cli.post("/ia/perguntar", json={"modo": "primeiro"})
    cli.post("/ia/perguntar", json={"modo": "primeiro"})
    assert len(chamadas) == 1
    assert cli.get("/ia/memoria?modo=primeiro").get_json()["ok"] is True  # abrir a tela não chama
    assert len(chamadas) == 1
    db.session.add(Tarefa(titulo="Nova tarefa"))
    db.session.commit()
    assert cli.get("/ia/memoria?modo=primeiro").get_json()["ok"] is False
    cli.post("/ia/perguntar", json={"modo": "primeiro"})
    assert len(chamadas) == 2
    from rotina.ia import estatisticas_cache
    assert estatisticas_cache()["tokens_economizados"] >= 500


def test_timer_rodando_nao_invalida_cache(app, cli, monkeypatch):
    chamadas = _ia_falsa(app, monkeypatch)
    t = Tarefa(titulo="A")
    db.session.add(t)
    db.session.commit()
    s = sv.iniciar_timer(t)
    cli.post("/ia/perguntar", json={"modo": "semana"})
    s.inicio = s.inicio - timedelta(minutes=3)  # alguns minutos a mais de timer
    db.session.commit()
    cli.post("/ia/perguntar", json={"modo": "semana"})
    assert len(chamadas) == 1


def test_calendario(app, cli):
    from rotina import _semear
    _semear()
    t = Tarefa(titulo="Entrega", prazo=hoje())
    db.session.add(t)
    db.session.commit()
    r = cli.get("/calendario")
    assert r.status_code == 200 and "Entrega" in r.get_data(as_text=True)
    for url in ["/calendario?mes=2026-01", f"/calendario?dia={hoje().isoformat()}",
                "/calendario?mes=lixo", f"/calendario?dia={(hoje() + timedelta(days=40)).isoformat()}"]:
        assert cli.get(url).status_code == 200, url
    semanas = sv.calendario_mes(hoje().year, hoje().month)
    dia = next(c for s in semanas for c in s if c["data"] == hoje())
    assert dia["prazos"][0].titulo == "Entrega" and dia["previstos"] > 0


# ---------------------------------------------------------------- projetos, evolução, migração

def test_projetos_crud_e_numeros(app, cli):
    from rotina.modelos import Projeto
    from rotina import estatisticas as est
    r = cli.post("/projetos/novo", data={"nome": "ESTUDOS", "cor": "#5b8fe0", "descricao": "cursos e leituras"})
    p = Projeto.query.one()
    assert r.status_code == 302 and p.descricao == "cursos e leituras"
    db.session.add_all([Tarefa(titulo="a", projeto_id=p.id),
                        Tarefa(titulo="b", projeto_id=p.id, prazo=hoje() - timedelta(days=1)),
                        Tarefa(titulo="c", projeto_id=p.id, status="feito", concluida_em=agora())])
    db.session.commit()
    res = est.resumo_projeto(p)
    assert (res["total"], res["abertas"], res["concluidas"], res["atrasadas"]) == (3, 2, 1, 1)
    assert round(res["progresso"], 2) == 0.33
    assert cli.get("/projetos/").status_code == 200
    pagina = cli.get(f"/projetos/{p.id}").get_data(as_text=True)
    assert "ESTUDOS" in pagina and "<svg" in pagina
    cli.post(f"/projetos/{p.id}/editar", data={"nome": "ESTUDOS 2", "cor": "#2fae78", "descricao": ""})
    assert db.session.get(Projeto, p.id).nome == "ESTUDOS 2"
    assert cli.post(f"/projetos/{p.id}/excluir").status_code == 400  # só arquivado
    cli.post(f"/projetos/{p.id}/arquivar")
    cli.post(f"/projetos/{p.id}/excluir")
    assert Projeto.query.count() == 0 and Tarefa.query.filter(Tarefa.projeto_id.is_(None)).count() == 3


def test_tarefas_filtros_e_contagens(app, cli):
    db.session.add_all([Tarefa(titulo="x"), Tarefa(titulo="y", status="feito", concluida_em=agora())])
    db.session.commit()
    html = cli.get("/tarefas?status=abertas").get_data(as_text=True)
    assert "segmentado" in html and 'class="contagem">1<' in html
    assert cli.get("/tarefas?status=lixo&projeto=avulso").status_code == 200


def test_evolucao_series(app, cli):
    from rotina import estatisticas as est
    h = novo_habito(dias_atras=5)
    marcar(h, 1)
    marcar(h, 2, "minimo")
    t = Tarefa(titulo="t", status="feito", concluida_em=agora() - timedelta(days=1))
    t.criada_em = agora() - timedelta(days=3)
    db.session.add(t)
    db.session.commit()
    dias = est.dias_ate_hoje(7)
    hab = {x["data"]: x for x in est.serie_habitos(dias)}
    assert hab[hoje() - timedelta(days=1)]["feito"] == 1 and hab[hoje() - timedelta(days=2)]["minimo"] == 1
    tar = {x["data"]: x for x in est.serie_tarefas(dias)}
    assert tar[hoje() - timedelta(days=2)]["a_fazer"] == 1
    assert tar[hoje() - timedelta(days=1)]["concluidas"] == 1 and tar[hoje() - timedelta(days=1)]["a_fazer"] == 0
    for n in (7, 14, 30, 90, 999):
        r = cli.get(f"/evolucao?dias={n}")
        assert r.status_code == 200 and "<svg" in r.get_data(as_text=True)


def test_grafico_escapa_texto():
    from rotina import graficos
    svg = graficos.barras(["<b>"], [{"nome": "x", "cor": "#2fae78", "valores": [3]}], titulo='"x"')
    assert "&lt;b&gt;" in svg and "<b>" not in svg and "&#34;x&#34;" in svg


def test_migracao_adiciona_coluna(tmp_path):
    import sqlite3
    caminho = tmp_path / "velho.db"
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE projeto (id INTEGER PRIMARY KEY, nome VARCHAR(80) NOT NULL, cor VARCHAR(7) NOT NULL, "
                "arquivado BOOLEAN NOT NULL, criado_em DATETIME NOT NULL)")
    con.execute("INSERT INTO projeto VALUES (1, 'Antigo', '#fff000', 0, '2026-09-01 10:00:00')")
    con.commit()
    con.close()
    app2 = criar_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{caminho}", "SEMEAR": False})
    with app2.app_context():
        from rotina.modelos import Projeto
        p = db.session.get(Projeto, 1)
        assert p.nome == "Antigo" and p.descricao == ""


def test_graficos_v13(app, cli):
    from rotina import estatisticas as est
    from rotina.modelos import Projeto
    redes = novo_habito(nome="Redes", tipo="numero", unidade="min", direcao="max")
    marcar(redes, 1, valor=40)
    h = novo_habito(dias_atras=20)
    for d in (1, 2, 3):          # 3 de 7 nesta semana
        marcar(h, d)
    for d in (8, 9, 10, 11, 12, 13):  # 6 de 7 na anterior
        marcar(h, d)
    comp = {x["habito"].id: x for x in est.comparacao_semanas()}[h.id]
    assert round(comp["antes"], 2) == 0.86 and round(comp["agora"], 2) == 0.43 and comp["delta"] < 0
    p = Projeto(nome="P", cor="#5b8fe0")
    db.session.add(p)
    db.session.commit()
    t1, t2 = Tarefa(titulo="a", projeto_id=p.id), Tarefa(titulo="b")
    db.session.add_all([t1, t2])
    db.session.commit()
    ini = agora() - timedelta(hours=3)
    db.session.add_all([SessaoTimer(tarefa_id=t1.id, inicio=ini, fim=ini + timedelta(minutes=50), focada=True),
                        SessaoTimer(tarefa_id=t2.id, inicio=ini, fim=ini + timedelta(minutes=10))])
    db.session.commit()
    tp = est.tempo_por_projeto(est.dias_ate_hoje(7))
    assert tp[0]["projeto"].nome == "P" and tp[0]["segundos"] == 3000 and tp[1]["projeto"] is None
    serie = est.serie_numero(redes, est.dias_ate_hoje(3))
    assert [x["valor"] for x in serie] == [None, 40, None]
    html = cli.get("/evolucao?dias=14").get_data(as_text=True)
    assert "Esta semana × semana anterior" in html and "Tempo por projeto" in html and "média 40" in html
