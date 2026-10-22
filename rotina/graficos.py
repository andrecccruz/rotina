"""Gráficos de barras em SVG gerados no servidor, sem bibliotecas externas e sem internet.

Regras visuais (iguais em todos os gráficos):
- barras de no máximo 24px, com 4px de arredondamento na ponta e base reta;
- 2px de folga na cor do fundo entre segmentos empilhados e entre barras vizinhas;
- grade horizontal fina e discreta, um eixo só;
- cada coluna tem uma área de hover maior que a barra, com `data-tip` para o tooltip;
- texto nunca usa a cor da série (legenda com amostra colorida ao lado).
"""
import math
from markupsafe import Markup, escape

LARGURA = 540
ESQ, DIR, TOPO, BASE = 34, 8, 12, 26
FOLGA = 2


def _passo_limpo(maximo, marcas=4):
    if maximo <= 0:
        return 1, 1
    bruto = maximo / marcas
    ordem = 10 ** math.floor(math.log10(bruto))
    for m in (1, 2, 2.5, 5, 10):
        passo = m * ordem
        if passo >= bruto:
            break
    passo = max(1, passo)
    teto = math.ceil(maximo / passo) * passo
    return passo, teto


def _barra(x, y_topo, largura, y_base, raio=4, arred=True):
    """Caminho de uma barra com a ponta arredondada e a base reta."""
    altura = y_base - y_topo
    if altura <= 0 or largura <= 0:
        return ""
    r = min(raio, largura / 2, altura) if arred else 0
    return (f"M{x:.1f},{y_base:.1f} V{y_topo + r:.1f} Q{x:.1f},{y_topo:.1f} {x + r:.1f},{y_topo:.1f} "
            f"H{x + largura - r:.1f} Q{x + largura:.1f},{y_topo:.1f} {x + largura:.1f},{y_topo + r:.1f} "
            f"V{y_base:.1f} Z")


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}".replace(".", ",")


def barras(rotulos, series, modo="simples", trilha=None, referencia=None, altura=210,
           unidade="", dicas=None, titulo=""):
    """rotulos: textos do eixo x. series: [{nome, cor, valores}].
    modo: 'simples' | 'empilhado' | 'agrupado'. trilha: valores de fundo (ex.: previstos).
    referencia: (valor, texto) para uma linha de meta. dicas: texto do tooltip por coluna."""
    n = len(rotulos)
    if n == 0:
        return Markup("")
    if modo == "empilhado":
        topo_dados = max((sum(s["valores"][i] for s in series) for i in range(n)), default=0)
    else:
        topo_dados = max((max(s["valores"]) for s in series if s["valores"]), default=0)
    if trilha:
        topo_dados = max(topo_dados, max(trilha))
    if referencia:
        topo_dados = max(topo_dados, referencia[0])
    passo, teto = _passo_limpo(topo_dados or 1)

    dir_ = 76 if referencia else DIR  # espaço à direita para o rótulo da meta/média
    area_l = LARGURA - ESQ - dir_
    area_h = altura - TOPO - BASE
    fatia = area_l / n
    y = lambda v: TOPO + area_h - (v / teto) * area_h  # noqa: E731
    y0 = y(0)

    p = [f'<svg class="grafico" viewBox="0 0 {LARGURA} {altura}" role="img" '
         f'aria-label="{escape(titulo)}" preserveAspectRatio="xMidYMid meet">']
    # grade
    v = 0
    while v <= teto + 1e-9:
        yy = y(v)
        p.append(f'<line class="g-grade" x1="{ESQ}" x2="{LARGURA - dir_}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        p.append(f'<text class="g-eixo" x="{ESQ - 6}" y="{yy + 3.5:.1f}" text-anchor="end">{_fmt(v)}</text>')
        v += passo
    # rótulos do eixo x (espaçados para não colidir)
    a_cada = 1 if n <= 10 else (2 if n <= 16 else math.ceil(n / 8))
    for i, rot in enumerate(rotulos):
        ultimo = i == n - 1
        if (i % a_cada == 0 and (ultimo or n - 1 - i >= a_cada)) or ultimo:
            cx = ESQ + fatia * (i + 0.5)
            p.append(f'<text class="g-eixo" x="{cx:.1f}" y="{altura - 8}" text-anchor="middle">{escape(rot)}</text>')

    for i in range(n):
        x0 = ESQ + fatia * i
        cx = x0 + fatia / 2
        if trilha:
            lb = min(24, fatia * 0.62)
            p.append(f'<path class="g-trilha" d="{_barra(cx - lb / 2, y(trilha[i]), lb, y0)}"/>')
        if modo == "empilhado":
            lb = min(24, fatia * 0.62)
            base = y0
            visiveis = [s for s in series if s["valores"][i] > 0]
            for k, s in enumerate(visiveis):
                topo = y(sum(t["valores"][i] for t in visiveis[:k + 1]))
                ultimo = k == len(visiveis) - 1
                fundo = base - (FOLGA if k > 0 else 0)
                p.append(f'<path fill="{s["cor"]}" d="{_barra(cx - lb / 2, topo, lb, fundo, arred=ultimo)}"/>')
                base = topo
        elif modo == "agrupado":
            k = len(series)
            lb = min(12, (fatia * 0.7 - FOLGA * (k - 1)) / k)
            inicio = cx - (lb * k + FOLGA * (k - 1)) / 2
            for j, s in enumerate(series):
                xb = inicio + j * (lb + FOLGA)
                p.append(f'<path fill="{s["cor"]}" d="{_barra(xb, y(s["valores"][i]), lb, y0)}"/>')
        else:
            lb = min(24, fatia * 0.62)
            s = series[0]
            p.append(f'<path fill="{s["cor"]}" d="{_barra(cx - lb / 2, y(s["valores"][i]), lb, y0)}"/>')
        dica = dicas[i] if dicas else f"{rotulos[i]}: " + ", ".join(
            f'{s["nome"]} {_fmt(s["valores"][i])}{unidade}' for s in series)
        p.append(f'<rect class="g-alvo" x="{x0:.1f}" y="{TOPO}" width="{fatia:.1f}" height="{area_h}" '
                 f'data-tip="{escape(dica)}"/>')

    if referencia:
        yy = y(referencia[0])
        p.append(f'<line class="g-ref" x1="{ESQ}" x2="{LARGURA - dir_ + 4}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        p.append(f'<text class="g-ref-txt" x="{LARGURA - dir_ + 8}" y="{yy + 4:.1f}" text-anchor="start">'
                 f'{escape(referencia[1])}</text>')
    p.append(f'<line class="g-base" x1="{ESQ}" x2="{LARGURA - dir_}" y1="{y0:.1f}" y2="{y0:.1f}"/>')
    p.append("</svg>")
    return Markup("".join(p))
