"""Leitura do config.json e utilidades de data no fuso configurado."""
import json
import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PADRAO = {
    "nome_app": "Rotina",
    "porta": 5001,
    "host": "127.0.0.1",
    "fuso_horario": "America/Sao_Paulo",
    "dias_congelamento_funcionalidades": 14,
    "ia": {
        "ativa": False,
        "provedor": "azure_openai",
        "endpoint": "",
        "deployment": "",
        "api_version": "2024-10-21",
        "modelo": "",
        "timeout_segundos": 60,
        "enviar_journaling": False,
        "cache": True,
        "cache_dias": 30,
    },
}


def _mesclar(base, extra):
    saida = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(saida.get(k), dict):
            saida[k] = _mesclar(saida[k], v)
        else:
            saida[k] = v
    return saida


def carregar_config(caminho=None):
    caminho = caminho or os.path.join(RAIZ, "config.json")
    dados = {}
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    return _mesclar(PADRAO, dados)


_FUSO = ZoneInfo(PADRAO["fuso_horario"])


def definir_fuso(nome):
    global _FUSO
    _FUSO = ZoneInfo(nome)


def agora():
    """Data/hora local (sem tzinfo) — tudo no banco fica no fuso configurado."""
    return datetime.now(_FUSO).replace(tzinfo=None, microsecond=0)


def hoje():
    return agora().date()


DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIAS_LONGOS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_br(d):
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def data_curta(d):
    if not d:
        return ""
    return f"{d.day:02d} {MESES[d.month - 1]}"


def data_extenso(d):
    return f"{DIAS_LONGOS[d.weekday()]}, {d.day} de {MESES_LONGOS[d.month - 1]}"


def duracao(segundos):
    segundos = int(segundos or 0)
    h, resto = divmod(segundos, 3600)
    m = resto // 60
    if h:
        return f"{h}h{m:02d}"
    return f"{m} min"


def parse_data(texto):
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None
