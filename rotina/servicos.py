"""Regras do sistema: status dos hábitos, sequências, grade e timer único."""
from datetime import date, datetime, timedelta

from .configuracao import agora, hoje
from .modelos import db, Habito, Registro, SessaoTimer, Tarefa, Parametro, Fechamento

# ---------------------------------------------------------------- hábitos


def agendado(h, d):
    """O hábito é esperado neste dia? (semanal: qualquer dia pode contar)"""
    if h.frequencia == "dias":
        return d.weekday() in h.dias_lista
    return True


def nivel_por_valor(h, valor):
    if valor is None:
        return None
    if h.direcao == "max":  # limite: quanto menos, melhor
        if h.meta is None:  # fase de medição: registrar já conta
            return "feito"
        if valor <= h.meta:
            return "feito"
        if h.meta_minima is not None and valor <= h.meta_minima:
            return "minimo"
        return None
    if h.meta is None:
        return "feito" if valor > 0 else None
    if valor >= h.meta:
        return "feito"
    if h.meta_minima is not None and valor >= h.meta_minima:
        return "minimo"
    return None


def niveis_intervalo(h, inicio, fim):
    """{data: 'feito'|'minimo'} para os dias em que o hábito foi cumprido, entre inicio e fim."""
    saida = {}
    if h.tipo in ("sim_nao", "numero"):
        regs = Registro.query.filter(Registro.habito_id == h.id,
                                     Registro.data >= inicio, Registro.data <= fim).all()
        for r in regs:
            nivel = nivel_por_valor(h, r.valor) if h.tipo == "numero" else r.nivel
            if nivel:
                saida[r.data] = nivel
        return saida

    ini_dt = datetime.combine(inicio, datetime.min.time())
    fim_dt = datetime.combine(fim + timedelta(days=1), datetime.min.time())

    if h.tipo == "auto_prioridade":
        tarefas = Tarefa.query.filter(Tarefa.prioritaria_em >= inicio,
                                      Tarefa.prioritaria_em <= fim).all()
        for t in tarefas:
            d = t.prioritaria_em
            if t.concluida_em and t.concluida_em.date() <= d:
                saida[d] = "feito"
            elif any(s.inicio.date() == d for s in t.sessoes):
                saida.setdefault(d, "minimo")
        return saida

    if h.tipo == "auto_flow":
        sessoes = SessaoTimer.query.filter(SessaoTimer.focada.is_(True),
                                           SessaoTimer.inicio >= ini_dt,
                                           SessaoTimer.inicio < fim_dt).all()
        por_dia = {}
        for s in sessoes:
            por_dia.setdefault(s.inicio.date(), []).append(s.segundos / 60)
        meta = h.meta if h.meta is not None else 60
        minima = h.meta_minima if h.meta_minima is not None else 25
        for d, minutos in por_dia.items():
            if sum(minutos) >= meta:
                saida[d] = "feito"
            elif max(minutos) >= minima:
                saida[d] = "minimo"
        return saida

    if h.tipo == "auto_journal":
        for f in Fechamento.query.filter(Fechamento.data >= inicio, Fechamento.data <= fim).all():
            if f.journaling.strip():
                saida[f.data] = "feito"
        return saida
    return saida


def _segunda(d):
    return d - timedelta(days=d.weekday())


def sequencias(h, niveis=None):
    """(atual, melhor, unidade) — unidade é 'dias' ou 'semanas'."""
    d0, d1 = h.criado_em, hoje()
    if niveis is None:
        niveis = niveis_intervalo(h, d0, d1)
    atual = melhor = 0

    if h.frequencia == "semanal":
        semana = _segunda(d0)
        while semana <= d1:
            fim_semana = semana + timedelta(days=6)
            feitos = sum(1 for d in niveis if semana <= d <= fim_semana)
            ok = feitos >= max(1, h.vezes_semana)
            em_andamento = fim_semana >= d1
            primeira = semana == _segunda(d0)
            if ok:
                atual += 1
            elif not (em_andamento or primeira):
                atual = 0
            melhor = max(melhor, atual)
            semana += timedelta(days=7)
        return atual, melhor, "semanas"

    d = d0
    while d <= d1:
        if agendado(h, d):
            if d in niveis:
                atual += 1
            elif d != d1:  # hoje ainda está em andamento: não quebra
                atual = 0
            melhor = max(melhor, atual)
        d += timedelta(days=1)
    return atual, melhor, "dias"


def grade(h, semanas=12, niveis=None):
    """Lista de semanas (segunda→domingo) com o estado de cada dia."""
    d1 = hoje()
    inicio = _segunda(d1) - timedelta(weeks=semanas - 1)
    if niveis is None:
        niveis = niveis_intervalo(h, inicio, d1)
    saida = []
    for w in range(semanas):
        linha = []
        for i in range(7):
            d = inicio + timedelta(days=w * 7 + i)
            if d > d1:
                estado = "futuro"
            elif d < h.criado_em:
                estado = "antes"
            elif d in niveis:
                estado = niveis[d]
            elif not agendado(h, d):
                estado = "livre"
            elif h.frequencia == "semanal":
                estado = "vazio"
            elif d == d1:
                estado = "pendente"
            else:
                estado = "falhou"
            linha.append({"data": d, "estado": estado})
        saida.append(linha)
    return saida


def progresso_semana(h, niveis=None):
    seg = _segunda(hoje())
    if niveis is None:
        niveis = niveis_intervalo(h, seg, hoje())
    return sum(1 for d in niveis if d >= seg)


def resumo_habito(h, semanas_grade=12):
    """Tudo que as telas precisam de um hábito, com uma consulta só ao histórico."""
    d1 = hoje()
    inicio = min(h.criado_em, _segunda(d1) - timedelta(weeks=semanas_grade - 1))
    niveis = niveis_intervalo(h, inicio, d1)
    atual, melhor, unidade = sequencias(h, niveis)
    reg = Registro.query.filter_by(habito_id=h.id, data=d1).first()
    return {
        "habito": h,
        "nivel_hoje": niveis.get(d1),
        "valor_hoje": reg.valor if reg else None,
        "agendado_hoje": agendado(h, d1),
        "atual": atual,
        "melhor": melhor,
        "unidade": unidade,
        "semana": progresso_semana(h, niveis),
        "grade": grade(h, semanas_grade, niveis),
    }


def registrar(h, d, nivel=None, valor=None):
    """Grava/limpa o registro manual de um dia. nivel='' ou None limpa sim/não."""
    reg = Registro.query.filter_by(habito_id=h.id, data=d).first()
    if h.tipo == "numero":
        if valor is None:
            if reg:
                db.session.delete(reg)
        else:
            reg = reg or Registro(habito_id=h.id, data=d)
            reg.valor = float(valor)
            reg.nivel = nivel_por_valor(h, reg.valor)
            db.session.add(reg)
    elif h.tipo == "sim_nao":
        if not nivel:
            if reg:
                db.session.delete(reg)
        else:
            reg = reg or Registro(habito_id=h.id, data=d)
            reg.nivel = nivel
            db.session.add(reg)
    db.session.commit()


def habitos_ativos():
    return Habito.query.filter_by(ativo=True).order_by(Habito.ordem, Habito.id).all()


# ---------------------------------------------------------------- timer único


def sessao_ativa():
    return SessaoTimer.query.filter_by(ativa=True).first()


def iniciar_timer(tarefa):
    atual = sessao_ativa()
    if atual and atual.tarefa_id == tarefa.id:
        return atual
    if atual:
        parar_timer(focada=None, commit=False)
        db.session.flush()
    s = SessaoTimer(tarefa_id=tarefa.id, inicio=agora(), ativa=True)
    if tarefa.status == "a_fazer":
        tarefa.status = "fazendo"
    db.session.add(s)
    db.session.commit()
    return s


def parar_timer(focada=None, proximo_passo=None, commit=True):
    s = sessao_ativa()
    if not s:
        return None
    s.fim = agora()
    s.ativa = None
    s.focada = focada
    if proximo_passo is not None and proximo_passo.strip():
        s.tarefa.proximo_passo = proximo_passo.strip()[:300]
    if commit:
        db.session.commit()
    return s


def concluir_tarefa(t):
    s = sessao_ativa()
    if s and s.tarefa_id == t.id:
        parar_timer(focada=None, commit=False)
    t.status = "feito"
    t.concluida_em = agora()
    db.session.commit()


def reabrir_tarefa(t):
    t.status = "a_fazer"
    t.concluida_em = None
    db.session.commit()


# ---------------------------------------------------------------- parâmetros


def parametro(chave, padrao=None):
    p = db.session.get(Parametro, chave)
    return p.valor if p else padrao


def definir_parametro(chave, valor):
    p = db.session.get(Parametro, chave) or Parametro(chave=chave, valor="")
    p.valor = str(valor)
    db.session.add(p)
    db.session.commit()


def data_inicio_uso():
    valor = parametro("data_inicio")
    if not valor:
        definir_parametro("data_inicio", hoje().isoformat())
        return hoje()
    return date.fromisoformat(valor)


def minutos_hoje():
    """Minutos de timer registrados hoje (inclui sessão rodando)."""
    ini = datetime.combine(hoje(), datetime.min.time())
    sessoes = SessaoTimer.query.filter(SessaoTimer.inicio >= ini).all()
    return sum(s.segundos for s in sessoes) // 60


# ---------------------------------------------------------------- calendário


def calendario_mes(ano, mes):
    """Semanas (seg→dom) do mês com o resumo de cada dia: hábitos, prazos, tempo e journaling."""
    import calendar
    from .modelos import Fechamento

    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, calendar.monthrange(ano, mes)[1])
    inicio = _segunda(primeiro)
    fim = ultimo + timedelta(days=6 - ultimo.weekday())
    d_hoje = hoje()
    ate = min(fim, d_hoje)

    habitos = habitos_ativos()
    niveis = {h.id: niveis_intervalo(h, inicio, ate) for h in habitos} if ate >= inicio else {}

    prazos = Tarefa.query.filter(Tarefa.prazo >= inicio, Tarefa.prazo <= fim).order_by(Tarefa.id).all()
    ini_dt = datetime.combine(inicio, datetime.min.time())
    fim_dt = datetime.combine(fim + timedelta(days=1), datetime.min.time())
    concluidas = Tarefa.query.filter(Tarefa.concluida_em >= ini_dt, Tarefa.concluida_em < fim_dt).all()
    prios = Tarefa.query.filter(Tarefa.prioritaria_em >= inicio, Tarefa.prioritaria_em <= fim).all()
    sessoes = SessaoTimer.query.filter(SessaoTimer.inicio >= ini_dt, SessaoTimer.inicio < fim_dt).all()
    fechs = {f.data: f for f in Fechamento.query.filter(Fechamento.data >= inicio, Fechamento.data <= fim)}

    semanas, d = [], inicio
    while d <= fim:
        linha = []
        for _ in range(7):
            previstos = [h for h in habitos if h.criado_em <= d and agendado(h, d)
                         and h.frequencia != "semanal"] if d <= d_hoje else []
            cumpridos = sum(1 for h in previstos if d in niveis.get(h.id, {}))
            seg_dia = [s for s in sessoes if s.inicio.date() == d]
            f = fechs.get(d)
            linha.append({
                "data": d,
                "no_mes": d.month == mes,
                "hoje": d == d_hoje,
                "futuro": d > d_hoje,
                "previstos": len(previstos),
                "cumpridos": cumpridos,
                "taxa": (cumpridos / len(previstos)) if previstos else None,
                "prazos": [t for t in prazos if t.prazo == d],
                "prioridade": next((t for t in prios if t.prioritaria_em == d), None),
                "concluidas": sum(1 for t in concluidas if t.concluida_em.date() == d),
                "minutos": sum(s.segundos for s in seg_dia) // 60,
                "focados": sum(s.segundos for s in seg_dia if s.focada) // 60,
                "journal": bool(f and f.journaling.strip()),
            })
            d += timedelta(days=1)
        semanas.append(linha)
    return semanas


def detalhe_dia(d):
    from .modelos import Fechamento
    ini = datetime.combine(d, datetime.min.time())
    fim = ini + timedelta(days=1)
    habitos = []
    for h in habitos_ativos():
        if h.criado_em > d:
            continue
        nivel = niveis_intervalo(h, d, d).get(d)
        habitos.append({"habito": h, "nivel": nivel, "previsto": agendado(h, d),
                        "registro": Registro.query.filter_by(habito_id=h.id, data=d).first()})
    return {
        "habitos": habitos,
        "prazos": Tarefa.query.filter_by(prazo=d).order_by(Tarefa.status, Tarefa.id).all(),
        "concluidas": Tarefa.query.filter(Tarefa.concluida_em >= ini, Tarefa.concluida_em < fim).all(),
        "prioridade": Tarefa.query.filter_by(prioritaria_em=d).first(),
        "sessoes": SessaoTimer.query.filter(SessaoTimer.inicio >= ini, SessaoTimer.inicio < fim)
                   .order_by(SessaoTimer.inicio).all(),
        "fechamento": Fechamento.query.filter_by(data=d).first(),
    }
