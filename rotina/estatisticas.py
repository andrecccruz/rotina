"""Números para a aba Evolução e para a página de cada projeto."""
from datetime import datetime, timedelta

from .configuracao import hoje
from .modelos import Projeto, SessaoTimer, Tarefa
from . import servicos as sv


def dias_ate_hoje(n):
    d1 = hoje()
    return [d1 - timedelta(days=n - 1 - i) for i in range(n)]


def _fim_do_dia(d):
    return datetime.combine(d + timedelta(days=1), datetime.min.time())


# ---------------------------------------------------------------- hábitos

def serie_habitos(dias):
    """Por dia: hábitos previstos, cumpridos como 'feito' e como 'mínimo'.
    Hábitos semanais ficam fora da conta diária (qualquer dia serve para eles)."""
    d0, d1 = dias[0], dias[-1]
    habitos = sv.habitos_ativos()
    niveis = {h.id: sv.niveis_intervalo(h, d0, d1) for h in habitos}
    saida = []
    for d in dias:
        previstos = [h for h in habitos if h.frequencia != "semanal" and h.criado_em <= d and sv.agendado(h, d)]
        feito = sum(1 for h in previstos if niveis[h.id].get(d) == "feito")
        minimo = sum(1 for h in previstos if niveis[h.id].get(d) == "minimo")
        saida.append({"data": d, "previstos": len(previstos), "feito": feito, "minimo": minimo})
    return saida


def taxa_por_habito(dias):
    """% de cumprimento de cada hábito ativo no período (mínimo conta)."""
    d0, d1 = dias[0], dias[-1]
    saida = []
    for h in sv.habitos_ativos():
        niveis = sv.niveis_intervalo(h, d0, d1)
        validos = [d for d in dias if d >= h.criado_em]
        if not validos:
            continue
        if h.frequencia == "semanal":
            esperado = max(1, round(h.vezes_semana * len(validos) / 7))
            feitos = sum(1 for d in niveis if d >= validos[0])
            taxa = min(1.0, feitos / esperado)
            detalhe = f"{feitos} de ~{esperado}"
        else:
            previstos = [d for d in validos if sv.agendado(h, d)]
            if not previstos:
                continue
            feitos = sum(1 for d in previstos if d in niveis)
            taxa = feitos / len(previstos)
            detalhe = f"{feitos} de {len(previstos)} dias"
        saida.append({"habito": h, "taxa": taxa, "detalhe": detalhe})
    return sorted(saida, key=lambda x: -x["taxa"])


# ---------------------------------------------------------------- tarefas e tempo

def serie_tarefas(dias, projeto_id=None):
    """Por dia: concluídas naquele dia e 'a fazer' (abertas no fim do dia)."""
    q = Tarefa.query
    if projeto_id is not None:
        q = q.filter(Tarefa.projeto_id == projeto_id)
    tarefas = q.all()
    saida = []
    for d in dias:
        fim = _fim_do_dia(d)
        concluidas = sum(1 for t in tarefas if t.concluida_em and t.concluida_em.date() == d)
        a_fazer = sum(1 for t in tarefas if t.criada_em < fim and (not t.concluida_em or t.concluida_em >= fim))
        criadas = sum(1 for t in tarefas if t.criada_em.date() == d)
        saida.append({"data": d, "concluidas": concluidas, "a_fazer": a_fazer, "criadas": criadas})
    return saida


def serie_foco(dias):
    ini = datetime.combine(dias[0], datetime.min.time())
    sessoes = SessaoTimer.query.filter(SessaoTimer.inicio >= ini).all()
    saida = []
    for d in dias:
        do_dia = [s for s in sessoes if s.inicio.date() == d]
        saida.append({"data": d,
                      "focado": sum(s.segundos for s in do_dia if s.focada) // 60,
                      "total": sum(s.segundos for s in do_dia) // 60})
    return saida


# ---------------------------------------------------------------- projetos

def resumo_projeto(p):
    d = hoje()
    tarefas = Tarefa.query.filter_by(projeto_id=p.id).all()
    abertas = [t for t in tarefas if t.status != "feito"]
    concluidas = len(tarefas) - len(abertas)
    prazos = sorted(t.prazo for t in abertas if t.prazo)
    return {
        "projeto": p,
        "total": len(tarefas),
        "a_fazer": sum(1 for t in abertas if t.status == "a_fazer"),
        "fazendo": sum(1 for t in abertas if t.status == "fazendo"),
        "abertas": len(abertas),
        "concluidas": concluidas,
        "atrasadas": sum(1 for t in abertas if t.prazo and t.prazo < d),
        "progresso": (concluidas / len(tarefas)) if tarefas else 0,
        "segundos": sum(t.segundos_totais for t in tarefas),
        "proximo_prazo": prazos[0] if prazos else None,
    }


def resumo_projetos(arquivados=False):
    ps = Projeto.query.filter_by(arquivado=arquivados).order_by(Projeto.nome).all()
    return [resumo_projeto(p) for p in ps]


# ---------------------------------------------------------------- v1.3

def serie_numero(h, dias):
    """Valores registrados de um hábito numérico por dia (None = sem registro)."""
    from .modelos import Registro
    regs = {r.data: r.valor for r in Registro.query.filter(
        Registro.habito_id == h.id, Registro.data >= dias[0], Registro.data <= dias[-1])}
    return [{"data": d, "valor": regs.get(d)} for d in dias]


def comparacao_semanas():
    """Cumprimento de cada hábito: últimos 7 dias × os 7 anteriores."""
    d1 = hoje()
    atual = [d1 - timedelta(days=6 - i) for i in range(7)]
    anterior = [d - timedelta(days=7) for d in atual]
    antes = {x["habito"].id: x for x in taxa_por_habito(anterior)}
    saida = []
    for x in taxa_por_habito(atual):
        a = antes.get(x["habito"].id)
        saida.append({"habito": x["habito"], "agora": x["taxa"],
                      "antes": a["taxa"] if a else None,
                      "delta": (x["taxa"] - a["taxa"]) if a else None})
    return saida


def tempo_por_projeto(dias):
    """Segundos de timer por projeto no período (avulsas incluídas), do maior ao menor."""
    ini = datetime.combine(dias[0], datetime.min.time())
    fim = _fim_do_dia(dias[-1])
    somas = {}
    for s in SessaoTimer.query.filter(SessaoTimer.inicio >= ini, SessaoTimer.inicio < fim).all():
        p = s.tarefa.projeto
        chave = p.id if p else None
        item = somas.setdefault(chave, {"projeto": p, "segundos": 0, "focados": 0})
        item["segundos"] += s.segundos
        if s.focada:
            item["focados"] += s.segundos
    return sorted(somas.values(), key=lambda x: -x["segundos"])
