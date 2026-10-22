"""Tabelas do banco (SQLite). Nomes em português."""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, UniqueConstraint, text

from .configuracao import agora

db = SQLAlchemy()


class Projeto(db.Model):
    __tablename__ = "projeto"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    cor = db.Column(db.String(7), nullable=False, default="#6aa9ff")
    descricao = db.Column(db.Text, nullable=False, default="", server_default="")
    arquivado = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=agora)


class Tarefa(db.Model):
    __tablename__ = "tarefa"
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=False, default="")
    projeto_id = db.Column(db.Integer, db.ForeignKey("projeto.id"), nullable=True)
    status = db.Column(db.String(10), nullable=False, default="a_fazer")  # a_fazer | fazendo | feito
    prazo = db.Column(db.Date, nullable=True)
    prioritaria_em = db.Column(db.Date, nullable=True)  # dia em que é a tarefa prioritária
    proximo_passo = db.Column(db.String(300), nullable=False, default="")
    criada_em = db.Column(db.DateTime, nullable=False, default=agora)
    concluida_em = db.Column(db.DateTime, nullable=True)

    projeto = db.relationship("Projeto", lazy="joined")
    sessoes = db.relationship("SessaoTimer", back_populates="tarefa", lazy="select",
                              cascade="all, delete-orphan")

    STATUS = {"a_fazer": "a fazer", "fazendo": "fazendo", "feito": "feito"}

    @property
    def segundos_totais(self):
        total = 0
        for s in self.sessoes:
            total += s.segundos
        return total


class Habito(db.Model):
    __tablename__ = "habito"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    # sim_nao | numero | auto_prioridade | auto_flow
    tipo = db.Column(db.String(20), nullable=False, default="sim_nao")
    unidade = db.Column(db.String(20), nullable=False, default="")
    # numero: "min" = quanto mais melhor (páginas) | "max" = limite (minutos de redes)
    direcao = db.Column(db.String(3), nullable=False, default="min")
    meta = db.Column(db.Float, nullable=True)          # nível "feito"
    meta_minima = db.Column(db.Float, nullable=True)   # nível "mínimo"
    versao_minima = db.Column(db.String(120), nullable=False, default="")
    # diaria | semanal | dias
    frequencia = db.Column(db.String(10), nullable=False, default="diaria")
    vezes_semana = db.Column(db.Integer, nullable=False, default=3)
    dias_semana = db.Column(db.String(20), nullable=False, default="")  # "0,2,4" (0 = segunda)
    no_fechamento = db.Column(db.Boolean, nullable=False, default=False)  # pedir no fechamento do dia
    ordem = db.Column(db.Integer, nullable=False, default=0)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.Date, nullable=False)
    arquivado_em = db.Column(db.Date, nullable=True)

    registros = db.relationship("Registro", back_populates="habito", lazy="select",
                                cascade="all, delete-orphan")

    TIPOS = {
        "sim_nao": "sim / não",
        "numero": "número",
        "auto_prioridade": "automático — tarefa prioritária",
        "auto_flow": "automático — sessões focadas",
        "auto_journal": "automático — journaling do fechamento",
    }

    @property
    def automatico(self):
        return self.tipo.startswith("auto_")

    @property
    def dias_lista(self):
        return [int(x) for x in self.dias_semana.split(",") if x.strip().isdigit()]


class Registro(db.Model):
    __tablename__ = "registro"
    id = db.Column(db.Integer, primary_key=True)
    habito_id = db.Column(db.Integer, db.ForeignKey("habito.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    nivel = db.Column(db.String(8), nullable=True)  # minimo | feito | None (registrado, não cumprido)
    valor = db.Column(db.Float, nullable=True)
    habito = db.relationship("Habito", back_populates="registros")
    __table_args__ = (UniqueConstraint("habito_id", "data", name="uq_registro_dia"),)


class SessaoTimer(db.Model):
    __tablename__ = "sessao_timer"
    id = db.Column(db.Integer, primary_key=True)
    tarefa_id = db.Column(db.Integer, db.ForeignKey("tarefa.id"), nullable=False)
    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime, nullable=True)
    ativa = db.Column(db.Boolean, nullable=True)  # True só na sessão rodando; NULL depois
    focada = db.Column(db.Boolean, nullable=True)
    tarefa = db.relationship("Tarefa", back_populates="sessoes")

    # Garante no banco: no máximo UMA sessão com ativa = 1.
    __table_args__ = (
        Index("ix_um_timer_ativo", "ativa", unique=True, sqlite_where=text("ativa = 1")),
    )

    @property
    def segundos(self):
        fim = self.fim or agora()
        return max(0, int((fim - self.inicio).total_seconds()))


class Ideia(db.Model):
    __tablename__ = "ideia"
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.String(500), nullable=False)
    etiqueta = db.Column(db.String(10), nullable=False, default="geral")  # geral | app
    criada_em = db.Column(db.DateTime, nullable=False, default=agora)
    situacao = db.Column(db.String(10), nullable=False, default="aberta")  # aberta | promovida | descartada
    tarefa_id = db.Column(db.Integer, db.ForeignKey("tarefa.id"), nullable=True)


class Fechamento(db.Model):
    __tablename__ = "fechamento"
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, unique=True)
    journaling = db.Column(db.Text, nullable=False, default="")
    salvo_em = db.Column(db.DateTime, nullable=False, default=agora)


class Parametro(db.Model):
    """Chave/valor interno (ex.: data em que o app começou a ser usado)."""
    __tablename__ = "parametro"
    chave = db.Column(db.String(50), primary_key=True)
    valor = db.Column(db.String(200), nullable=False)


class RespostaIA(db.Model):
    """Cache das respostas da IA, chaveado pelo hash do contexto enviado."""
    __tablename__ = "resposta_ia"
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(64), nullable=False, unique=True)
    funcao = db.Column(db.String(20), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    tokens = db.Column(db.Integer, nullable=True)
    usos = db.Column(db.Integer, nullable=False, default=0)  # vezes reaproveitada sem chamar a IA
    criada_em = db.Column(db.DateTime, nullable=False, default=agora)
