"""Aba Evolução: gráficos de acompanhamento por dia."""
from flask import Blueprint, current_app, render_template, request

from . import estatisticas as est
from . import graficos
from .configuracao import DIAS_SEMANA
from .modelos import Habito

bp = Blueprint("evolucao", __name__)

COR_FEITO, COR_MINIMO, COR_AFAZER = "#2fae78", "#8a7fd8", "#5b8fe0"
COR_CRIADAS, COR_NUMERO = "#c0873a", "#5b8fe0"


def _rotulo(d, n):
    return DIAS_SEMANA[d.weekday()] if n <= 7 else d.strftime("%d/%m")


@bp.route("/evolucao")
def painel():
    try:
        n = int(request.args.get("dias", 14))
    except ValueError:
        n = 14
    n = n if n in (7, 14, 30, 90) else 14
    dias = est.dias_ate_hoje(n)
    rot = [_rotulo(d, n) for d in dias]

    hab = est.serie_habitos(dias)
    g_hab = graficos.barras(
        rot,
        [{"nome": "feito", "cor": COR_FEITO, "valores": [x["feito"] for x in hab]},
         {"nome": "mínimo", "cor": COR_MINIMO, "valores": [x["minimo"] for x in hab]}],
        modo="empilhado", trilha=[x["previstos"] for x in hab], titulo="Hábitos cumpridos por dia",
        dicas=[f'{x["data"].strftime("%d/%m")} · {x["feito"]} feito · {x["minimo"]} mínimo · '
               f'{x["previstos"]} previstos' for x in hab])

    tar = est.serie_tarefas(dias)
    g_tar = graficos.barras(
        rot,
        [{"nome": "concluídas", "cor": COR_FEITO, "valores": [x["concluidas"] for x in tar]},
         {"nome": "a fazer", "cor": COR_AFAZER, "valores": [x["a_fazer"] for x in tar]}],
        modo="agrupado", titulo="Tarefas concluídas e a fazer por dia",
        dicas=[f'{x["data"].strftime("%d/%m")} · {x["concluidas"]} concluída(s) · {x["a_fazer"]} a fazer'
               f' · {x["criadas"]} criada(s)' for x in tar])

    foco = est.serie_foco(dias)
    flow = Habito.query.filter_by(tipo="auto_flow", ativo=True).first()
    meta_flow = (flow.meta or 60) if flow else None
    g_foco = graficos.barras(
        rot, [{"nome": "focado", "cor": COR_FEITO, "valores": [x["focado"] for x in foco]}],
        referencia=(meta_flow, f"meta {int(meta_flow)} min") if meta_flow else None,
        unidade=" min", titulo="Minutos focados por dia",
        dicas=[f'{x["data"].strftime("%d/%m")} · {x["focado"]} min focados de {x["total"]} no timer'
               for x in foco])

    # criadas × concluídas (o saldo mostra se a fila cresce ou encolhe)
    g_fluxo = graficos.barras(
        rot,
        [{"nome": "criadas", "cor": COR_CRIADAS, "valores": [x["criadas"] for x in tar]},
         {"nome": "concluídas", "cor": COR_FEITO, "valores": [x["concluidas"] for x in tar]}],
        modo="agrupado", titulo="Tarefas criadas e concluídas por dia",
        dicas=[f'{x["data"].strftime("%d/%m")} · {x["criadas"]} criada(s) · {x["concluidas"]} concluída(s)'
               for x in tar])
    saldo = sum(x["criadas"] for x in tar) - sum(x["concluidas"] for x in tar)

    # números dos hábitos (redes, checagens, leitura…), um gráfico por hábito
    numeros = []
    for h in Habito.query.filter_by(tipo="numero", ativo=True).order_by(Habito.ordem, Habito.id):
        serie = est.serie_numero(h, dias)
        valores = [x["valor"] for x in serie if x["valor"] is not None]
        media = sum(valores) / len(valores) if valores else None
        if h.meta is not None:
            ref = (h.meta, f"meta {graficos._fmt(h.meta)}")
        elif media is not None:
            ref = (round(media, 1), f"média {graficos._fmt(round(media, 1))}")
        else:
            ref = None
        numeros.append({
            "habito": h, "serie": serie, "media": media, "registros": len(valores),
            "grafico": graficos.barras(
                rot, [{"nome": h.nome, "cor": COR_NUMERO, "valores": [x["valor"] or 0 for x in serie]}],
                referencia=ref, altura=170, titulo=f"{h.nome} por dia",
                dicas=[f'{x["data"].strftime("%d/%m")} · ' + (f'{graficos._fmt(x["valor"])} {h.unidade}'
                       if x["valor"] is not None else "sem registro") for x in serie]),
        })

    projetos = est.tempo_por_projeto(dias)
    maior_proj = max((x["segundos"] for x in projetos), default=0)

    previstos = sum(x["previstos"] for x in hab)
    cumpridos = sum(x["feito"] + x["minimo"] for x in hab)
    resumo = {
        "taxa": round(100 * cumpridos / previstos) if previstos else None,
        "dias_completos": sum(1 for x in hab if x["previstos"] and x["feito"] + x["minimo"] >= x["previstos"]),
        "concluidas": sum(x["concluidas"] for x in tar),
        "a_fazer_hoje": tar[-1]["a_fazer"] if tar else 0,
        "a_fazer_inicio": tar[0]["a_fazer"] if tar else 0,
        "focado": sum(x["focado"] for x in foco),
    }
    return render_template(
        "evolucao.html", n=n, dias=dias, hab=hab, tar=tar, foco=foco,
        g_hab=g_hab, g_tar=g_tar, g_foco=g_foco, resumo=resumo,
        por_habito=est.taxa_por_habito(dias),
        g_fluxo=g_fluxo, saldo=saldo, numeros=numeros, semanas=est.comparacao_semanas(),
        projetos=projetos, maior_proj=maior_proj,
        cores={"feito": COR_FEITO, "minimo": COR_MINIMO, "afazer": COR_AFAZER,
               "criadas": COR_CRIADAS, "numero": COR_NUMERO})
