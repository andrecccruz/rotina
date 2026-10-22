"""IA somente leitura: monta o contexto a partir do banco e chama o provedor.

Nada aqui grava tarefas ou hábitos. A chave vem do .env e nunca vai ao navegador.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timedelta

import requests

from .configuracao import RAIZ, agora, hoje, data_extenso, duracao, DIAS_SEMANA
from .modelos import db, Fechamento, Registro, RespostaIA, SessaoTimer, Tarefa
from . import servicos as sv


class ErroIA(Exception):
    pass


SISTEMA = """Você é o assistente pessoal do app Rotina, usado por uma única pessoa para \
criar/retomar hábitos e terminar o que começa. Responda em português do Brasil, direto e curto.

Princípios que você segue:
- Começar pequeno vence planejar grande: sempre termine com um primeiro passo concreto \
que caiba em 5–10 minutos.
- Microtarefas, não nuvens: troque "estudar X" por ações verificáveis ("ler págs. 20–25").
- Uma coisa por vez. Nada de sugerir novas ferramentas, apps ou funcionalidades.
- Em dia ruim, a versão mínima do hábito vale e mantém a sequência.
- Sem sermão e sem culpa. Se algo deu errado, diga qual é o próximo comportamento certo.
- Use somente os dados fornecidos; não invente tarefas, prazos ou números.
- Você só lê e sugere. Não diga que criou, alterou ou agendou nada.

Formate com títulos curtos em **negrito** e listas com "- ". No máximo ~200 palavras, \
salvo quando pedirem detalhe."""


# ---------------------------------------------------------------- contexto

def _linha_tarefa(t, d):
    partes = [f"- [{t.id}] {t.titulo}"]
    if t.projeto:
        partes.append(f"(projeto: {t.projeto.nome})")
    partes.append(f"status: {Tarefa.STATUS.get(t.status, t.status)}")
    if t.prazo:
        atraso = (d - t.prazo).days
        rotulo = t.prazo.strftime("%d/%m")
        if atraso > 0:
            rotulo += f" — ATRASADA {atraso} dia(s)"
        elif atraso == 0:
            rotulo += " — vence HOJE"
        partes.append(f"prazo: {rotulo}")
    if t.prioritaria_em == d:
        partes.append("★ prioridade de hoje")
    if t.proximo_passo:
        partes.append(f"próximo passo anotado: “{t.proximo_passo}”")
    seg = t.segundos_totais
    if seg >= 450:  # só a partir de ~15 min, já arredondado
        partes.append(f"tempo já investido: ~{_arred(seg)}")
    return " | ".join(partes)


def contexto_tarefas(limite=40):
    d = hoje()
    abertas = (Tarefa.query.filter(Tarefa.status != "feito")
               .order_by(Tarefa.prazo.is_(None), Tarefa.prazo, Tarefa.id).limit(limite).all())
    if not abertas:
        return "Tarefas abertas: nenhuma."
    return "Tarefas abertas:\n" + "\n".join(_linha_tarefa(t, d) for t in abertas)


def contexto_habitos_hoje():
    linhas = []
    for h in sv.habitos_ativos():
        r = sv.resumo_habito(h, semanas_grade=1)
        if not r["agendado_hoje"]:
            continue
        estado = {"feito": "feito", "minimo": "mínimo feito"}.get(r["nivel_hoje"], "pendente")
        extra = f" (versão mínima: {h.versao_minima})" if h.versao_minima else ""
        if h.frequencia == "semanal":
            extra += f" — {r['semana']}/{h.vezes_semana} nesta semana"
        linhas.append(f"- {h.nome}: {estado}; sequência {r['atual']} {r['unidade']}{extra}")
    return "Hábitos de hoje:\n" + ("\n".join(linhas) if linhas else "- nenhum")


def contexto_semana(enviar_journaling=False):
    d1 = hoje()
    d0 = d1 - timedelta(days=6)
    linhas = [f"Período: {d0.strftime('%d/%m')} a {d1.strftime('%d/%m')} (hoje ainda em andamento)."]
    dias = [d0 + timedelta(days=i) for i in range(7)]
    linhas.append("Hábitos (por dia; F = feito, m = mínimo, · = não, – = não previsto):")
    for h in sv.habitos_ativos():
        niveis = sv.niveis_intervalo(h, d0, d1)
        marcas = []
        for d in dias:
            if d < h.criado_em or not sv.agendado(h, d):
                marcas.append("–")
            else:
                marcas.append({"feito": "F", "minimo": "m"}.get(niveis.get(d), "·"))
        texto = f"- {h.nome}: " + " ".join(f"{DIAS_SEMANA[d.weekday()]}:{m}" for d, m in zip(dias, marcas))
        if h.tipo == "numero":
            valores = {r.data: r.valor for r in Registro.query.filter(
                Registro.habito_id == h.id, Registro.data >= d0).all()}
            nums = [f"{valores[d]:g}" for d in dias if d in valores]
            if nums:
                texto += f" | valores ({h.unidade}): {', '.join(nums)}"
        linhas.append(texto)

    ini = datetime.combine(d0, datetime.min.time())
    sessoes = SessaoTimer.query.filter(SessaoTimer.inicio >= ini).all()
    total = sum(s.segundos for s in sessoes)
    focado = sum(s.segundos for s in sessoes if s.focada)
    fechadas = [s for s in sessoes if s.fim]
    linhas.append(f"Timer: ~{_arred(total)} no total, ~{_arred(focado)} marcados como focados, "
                  f"{len(fechadas)} sessões encerradas.")
    feitas = Tarefa.query.filter(Tarefa.concluida_em >= ini).all()
    linhas.append(f"Tarefas concluídas: {len(feitas)}" +
                  (": " + "; ".join(t.titulo for t in feitas[:15]) if feitas else ""))
    prios = Tarefa.query.filter(Tarefa.prioritaria_em >= d0, Tarefa.prioritaria_em <= d1).count()
    linhas.append(f"Dias com prioridade definida: {prios} de 7.")
    fechs = Fechamento.query.filter(Fechamento.data >= d0).order_by(Fechamento.data).all()
    linhas.append(f"Fechamentos do dia feitos: {len(fechs)} de 7.")
    if enviar_journaling:
        for f in fechs:
            if f.journaling.strip():
                linhas.append(f"Journaling {f.data.strftime('%d/%m')}: {f.journaling.strip()[:600]}")
    return "\n".join(linhas)


def _arred(segundos):
    """Arredonda para 15 min: o timer rodando não invalida o cache a cada minuto."""
    return duracao(round((segundos or 0) / 900) * 900)


def periodo_do_dia(hora=None):
    hora = agora().hour if hora is None else hora
    return "manhã" if hora < 12 else ("tarde" if hora < 18 else "noite")


def cabecalho():
    a = agora()
    return f"Agora: {data_extenso(a.date())}, {a.strftime('%H:%M')} ({periodo_do_dia(a.hour)})."


def _pacote(funcao, corpo_estavel, instrucao, partes_chave):
    """Monta as mensagens e a chave de cache.

    Ordem pensada para cache de prompt do provedor: sistema (fixo) -> contexto -> pedido,
    com a hora exata por último. A chave local ignora a hora exata e usa só o que muda
    a resposta (dados + dia/período)."""
    usuario = "\n".join(corpo_estavel + [instrucao, "", cabecalho()])
    mensagens = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}]
    base = json.dumps([funcao, SISTEMA, corpo_estavel, instrucao, partes_chave], ensure_ascii=False)
    return mensagens, hashlib.sha256(base.encode("utf-8")).hexdigest()


def mensagens_explicar(t):
    corpo = ["Tarefa a explicar:", f"- {t.titulo}"]
    if t.projeto:
        corpo.append(f"Projeto: {t.projeto.nome}")
    if t.prazo:
        corpo.append(f"Prazo: {t.prazo.strftime('%d/%m/%Y')}")
    if t.proximo_passo:
        corpo.append(f"Próximo passo anotado: {t.proximo_passo}")
    if t.descricao:
        corpo.append(f"Descrição: {t.descricao}")
    instrucao = ("\nExplique esta tarefa para mim: **O que é** (2–3 frases), **Passos** (3 a 6 "
                 "microtarefas concretas, em ordem) e **Comece agora** (o primeiro passo de 10 "
                 "minutos). Se o título for vago demais para explicar, diga o que falta e sugira "
                 "como reescrever.")
    # explicação não depende do dia: a chave usa só o conteúdo da tarefa
    return _pacote("explicar", corpo, instrucao, [])


def mensagens_painel(modo, pergunta, cfg_ia):
    corpo = [contexto_tarefas(), contexto_habitos_hoje()]
    chave = [hoje().isoformat()]
    if modo == "semana":
        corpo.append(contexto_semana(cfg_ia.get("enviar_journaling")))
        instrucao = ("\nComo foi minha semana? Responda com **O que foi bem**, **O que caiu** e "
                     "**Um ajuste para a próxima semana** (um só, pequeno). Compare com os números acima.")
    elif modo == "livre" and pergunta:
        instrucao = f"\nMinha pergunta: {pergunta[:1500]}"
        chave.append(periodo_do_dia())
    else:
        instrucao = ("\nO que eu faço primeiro? Olhe prazos, a prioridade de hoje e os hábitos "
                     "pendentes. Responda com **Agora** (uma tarefa e o primeiro passo), **Depois** "
                     "(ordem sugerida para o resto do dia, com blocos de horário aproximados a partir "
                     "da hora indicada no fim) e **Pode esperar** (o que não precisa ser hoje).")
        chave.append(periodo_do_dia())
    return _pacote(modo, corpo, instrucao, chave)


# ---------------------------------------------------------------- chamada

def _registrar_log(funcao, ok, inicio, uso=None, erro=None):
    try:
        caminho = os.path.join(RAIZ, "dados", "ia_log.jsonl")
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "quando": agora().isoformat(), "funcao": funcao, "ok": ok,
                "segundos": round(time.time() - inicio, 2), "uso": uso, "erro": erro,
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


def chamar(cfg_ia, mensagens, funcao="?"):
    if not cfg_ia.get("ativa"):
        raise ErroIA("A IA está desligada. Ative em config.json (ia.ativa = true).")
    provedor = cfg_ia.get("provedor", "azure_openai")
    endpoint = (cfg_ia.get("endpoint") or "").rstrip("/")
    if not endpoint or "SEU-RECURSO" in endpoint:
        raise ErroIA("Endpoint da IA não configurado em config.json.")
    corpo = {"messages": mensagens}

    if provedor == "azure_openai":
        chave = os.environ.get("AZURE_OPENAI_API_KEY", "")
        cabecalhos = {"api-key": chave, "Content-Type": "application/json"}
        if "/openai/v1" in endpoint:  # formato novo da Azure (compatível com OpenAI)
            url = endpoint + "/chat/completions"
            corpo["model"] = cfg_ia.get("modelo") or cfg_ia.get("deployment")
        else:
            url = (f"{endpoint}/openai/deployments/{cfg_ia.get('deployment')}"
                   f"/chat/completions?api-version={cfg_ia.get('api_version', '2024-10-21')}")
    else:  # openai_compativel
        chave = os.environ.get("IA_API_KEY", "")
        cabecalhos = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
        url = endpoint + "/chat/completions"
        corpo["model"] = cfg_ia.get("modelo")
    if not chave:
        raise ErroIA("Chave da IA ausente no .env.")

    inicio = time.time()
    try:
        resp = requests.post(url, headers=cabecalhos, json=corpo,
                             timeout=int(cfg_ia.get("timeout_segundos", 60)))
    except requests.RequestException as e:
        _registrar_log(funcao, False, inicio, erro=type(e).__name__)
        raise ErroIA("Não consegui falar com o provedor de IA (rede ou timeout).")
    if resp.status_code >= 400:
        _registrar_log(funcao, False, inicio, erro=f"HTTP {resp.status_code}")
        detalhe = ""
        try:
            detalhe = resp.json().get("error", {}).get("message", "")[:200]
        except ValueError:
            pass
        raise ErroIA(f"O provedor recusou a chamada (HTTP {resp.status_code}). {detalhe}".strip())
    try:
        dados = resp.json()
        texto = dados["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError):
        _registrar_log(funcao, False, inicio, erro="resposta inesperada")
        raise ErroIA("Resposta inesperada do provedor.")
    _registrar_log(funcao, True, inicio, uso=dados.get("usage"))
    return texto.strip(), (dados.get("usage") or {}).get("total_tokens")


# ---------------------------------------------------------------- cache

def _validade(cfg_ia):
    return timedelta(days=float(cfg_ia.get("cache_dias", 30)))


def consultar_cache(cfg_ia, chave):
    if not cfg_ia.get("cache", True):
        return None
    r = RespostaIA.query.filter_by(chave=chave).first()
    if r and r.criada_em >= agora() - _validade(cfg_ia):
        return r
    return None


def responder(cfg_ia, funcao, mensagens, chave, forcar=False):
    """Devolve {texto, cache, criada_em}. Só chama o provedor se não houver resposta
    válida para exatamente este contexto (ou se o usuário pediu para refazer)."""
    if not cfg_ia.get("ativa"):
        raise ErroIA("A IA está desligada. Ative em config.json (ia.ativa = true).")
    r = None if forcar else consultar_cache(cfg_ia, chave)
    if r:
        r.usos += 1
        db.session.commit()
        return {"texto": r.texto, "cache": True, "criada_em": r.criada_em}
    texto, tokens = chamar(cfg_ia, mensagens, funcao)
    if cfg_ia.get("cache", True):
        RespostaIA.query.filter(RespostaIA.criada_em < agora() - _validade(cfg_ia)).delete()
        r = RespostaIA.query.filter_by(chave=chave).first() or RespostaIA(chave=chave, funcao=funcao, usos=0)
        r.texto, r.tokens, r.criada_em = texto, tokens, agora()
        db.session.add(r)
        db.session.commit()
    return {"texto": texto, "cache": False, "criada_em": agora()}


def estatisticas_cache():
    itens = RespostaIA.query.all()
    return {
        "respostas": len(itens),
        "reaproveitadas": sum(i.usos for i in itens),
        "tokens_economizados": sum((i.tokens or 0) * i.usos for i in itens),
    }
