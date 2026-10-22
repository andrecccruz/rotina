# Prompt — Rotina (rastreador de hábitos com tarefas em volta)

> Use este prompt para recriar o sistema do zero ou para uma IA de código (Fable, Claude Code)
> evoluir o projeto existente sem perder as decisões. Se o código já existir, **leia-o antes**
> e trate este documento como a especificação: onde divergirem, pergunte antes de mudar.

---

## 1. Contexto e objetivo

Você vai construir o **Rotina**, um sistema pessoal, em português do Brasil, para **uma única
pessoa** criar hábitos novos, retomar hábitos antigos e acompanhar tudo isso. As tarefas existem
para apoiar os hábitos, não o contrário.

Apps desse tipo costumam ser abandonados por dois motivos:

1. **O hábito de usar o sistema não se forma.** Abrir e registrar precisa ser rápido. A tela Hoje
   resolve 90% do uso diário, e o fechamento do dia leva cerca de 2 minutos.
2. **Funcionalidades demais** fazem o desenvolvimento travar. O próprio sistema
   precisa proteger o escopo (veja a Garagem e o congelamento de 14 dias).

**Princípios de produto** (valem para UI, textos e prompts da IA):
- Começar pequeno vence planejar grande. Cada hábito tem uma **versão mínima** que conta em dia ruim.
- Uma coisa por vez: o **timer é único**.
- Capturar em vez de trocar de tarefa: toda ideia nova vai para a **Garagem**.
- Terminar cada sessão anotando o **próximo passo concreto**.
- Sem culpa e sem gamificação exagerada. Sequência sim; pontos, medalhas e confete, não.

---

## 2. Restrições técnicas (obrigatórias)

- **Roda 100% local no Windows**: `python app.py` → `http://127.0.0.1:5001`.
- Sem nuvem, sem login, sem serviço pago obrigatório. A arquitetura precisa permitir publicar
  depois em rede interna ou VPS sem reescrever.
- **Stack:** Python 3.11+, Flask com blueprints, SQLite via Flask-SQLAlchemy, Jinja2 +
  HTML/CSS/JS **vanilla**. Sem React/Vue, sem build step, sem CDN: tudo funciona offline.
  Dependências: `Flask`, `Flask-SQLAlchemy`, `python-dotenv`, `requests`, `tzdata`.
- Tabelas, campos, rotas, variáveis de domínio e UI em **português**. Explicações longas vão em
  arquivos `.md` separados, não em comentários enormes no código.
- Configuração em `config.json`, explicada campo a campo em `CONFIG.md`. Segredos só no `.env`.
- Colunas novas em tabelas existentes entram por uma lista `MIGRACOES` aplicada na inicialização
  (`ALTER TABLE … ADD COLUMN`), porque `create_all()` não altera tabelas existentes.
- Fuso horário configurável (padrão `America/Sao_Paulo`). "Hoje" é sempre calculado nesse fuso.
  Datas no banco são locais e sem tzinfo.
- Incluir `iniciar.bat` (cria o venv, instala, abre o navegador, sobe o servidor) com fim de
  linha CRLF.

---

## 3. Modelo de dados (SQLite)

| Tabela | Campos principais | Observações |
|---|---|---|
| `projeto` | nome, cor (#hex), **descricao**, arquivado | Tarefa sem projeto = "avulsa". Excluir só projeto arquivado; as tarefas viram avulsas |
| `tarefa` | titulo, descricao, projeto_id, status (`a_fazer`/`fazendo`/`feito`), prazo, **prioritaria_em** (data), **proximo_passo**, criada_em, concluida_em | No máximo uma tarefa prioritária por dia |
| `habito` | nome, **tipo**, unidade, **direcao** (`min`/`max`), meta, meta_minima, versao_minima, **frequencia** (`diaria`/`semanal`/`dias`), vezes_semana, dias_semana ("0,2,4", 0 = segunda), no_fechamento, ordem, ativo, criado_em, arquivado_em | |
| `registro` | habito_id, data, nivel (`minimo`/`feito`), valor | Único por (hábito, data). Só para tipos manuais |
| `sessao_timer` | tarefa_id, inicio, fim, **ativa**, focada | **Índice único parcial `WHERE ativa = 1`**: o banco impede dois timers. Ao parar, `ativa = NULL` (sem default na coluna) |
| `ideia` | texto, etiqueta (`geral`/`app`), situacao (`aberta`/`promovida`/`descartada`), tarefa_id | |
| `fechamento` | data (única), journaling, salvo_em | |
| `parametro` | chave, valor | Ex.: `data_inicio` (primeiro uso, para o congelamento) |
| `resposta_ia` | chave (sha256, única), funcao, texto, tokens, usos, criada_em | Cache da IA |

### Tipos de hábito

| Tipo | Como é cumprido |
|---|---|
| `sim_nao` | Botões "mínimo" / "feito" (clicar de novo desmarca) |
| `numero` | Valor do dia. Direção `min` (páginas): valor ≥ meta = feito, ≥ meta_minima = mínimo. Direção `max` (limite, ex.: minutos de redes): valor ≤ meta = feito, ≤ meta_minima = mínimo. **Limite sem meta = fase de medição: registrar já conta como feito** |
| `auto_prioridade` | Feito se a tarefa ★ do dia foi concluída até aquele dia. Mínimo se houve sessão de timer nela naquele dia |
| `auto_flow` | Soma das sessões marcadas como focadas no dia ≥ meta (padrão 60 min) = feito. Uma sessão focada ≥ meta_minima (padrão 25 min) = mínimo |
| `auto_journal` | Feito se o fechamento do dia tem journaling não vazio |

### Hábitos criados no primeiro uso (editáveis)

1. Redes sociais: número, `max`, "min", sem meta (medição), no fechamento
2. Checagens do celular: número, `max`, "desbloqueios", sem meta, no fechamento
3. Leitura: número, `min`, "páginas", meta 10, mínimo 2, no fechamento
4. Concluir a prioridade do dia: `auto_prioridade`
5. Estado de flow: `auto_flow`, 60 / 25
6. Ambiente organizado: sim/não, versão mínima "arrumar a cama", no fechamento
7. Desacelerar à noite: sim/não, dias seg–sex, versão mínima "10 min sem tela antes de dormir", no fechamento
8. Journaling: `auto_journal`

---

## 4. Regras de negócio

- **Mínimo e feito mantêm a sequência.**
- **Sequência diária / dias específicos:** conta os dias previstos seguidos com cumprimento.
  Dias não previstos são pulados. **Hoje ainda não cumprido não quebra.**
- **Sequência semanal ("X vezes por semana"):** conta semanas (seg–dom) com pelo menos X
  cumprimentos. A semana em andamento e a primeira semana (parcial) não quebram.
- Mostrar sempre a **sequência atual** e a **melhor sequência**.
- **Arquivar** guarda todo o histórico. **Reativar** traz o hábito de volta com a melhor
  sequência preservada. Excluir só é possível para hábito arquivado, com confirmação.
- **Timer único:** iniciar outro timer encerra o atual (sem perguntar "focada") e avisa.
  Parar pergunta "foi focada?" e "próximo passo?", e o próximo passo é gravado na tarefa.
  Concluir a tarefa com o timer dela rodando encerra o timer. Iniciar coloca a tarefa em "fazendo".
- **Prioridade:** definir a prioridade de um dia remove a de outra tarefa no mesmo dia.
- **Congelamento de funcionalidades:** `data_inicio` + `dias_congelamento_funcionalidades`
  (padrão 14). Até essa data, a Garagem mostra o aviso e pede confirmação para promover ideia
  `app`. Depois, mostra "revisão liberada: escolha **uma**".
- Na captura rápida, texto começando com `app:` vira ideia com etiqueta `app`.

---

## 5. Telas

Tema escuro "terminal/industrial" limpo: tokens CSS em `:root`, fonte do sistema, monoespaçada
para números, responsivo até 390 px sem rolagem horizontal. No celular o topo não fica fixo e o
menu vira uma linha rolável. Sem nenhum recurso externo.

Em todas as telas:
- Barra superior com navegação e o campo **💡 capturar ideia** (atalho: tecla `/`).
- Com o timer rodando, uma **faixa verde** com o relógio ao vivo, o nome da tarefa e o botão
  "parar", que abre o diálogo de encerramento. O título da aba mostra o tempo.

1. **Hoje** (`/`): data por extenso; números do dia (hábitos cumpridos/previstos, tarefas
   concluídas, tempo no timer); ★ prioridade (se não houver, um select para definir); tarefas
   atrasadas, que vencem hoje e em andamento; campo "+ tarefa para hoje"; hábitos previstos com
   o check adequado a cada tipo, a sequência e a meta; caixa do **Assistente** (se a IA estiver ativa).
2. **Hábitos** (`/habitos/`): cartão por hábito com frequência, meta, check de hoje, editar,
   arquivar, e **grade das últimas 12 semanas** (colunas = semanas, linhas = dias; cores:
   feito, mínimo, não feito, hoje, não previsto, antes de existir). Seção de arquivados com
   reativar/excluir. Formulário com todos os campos e a explicação da fase de medição.
3. **Tarefas** (`/tarefas`): lista em largura total. Filtros numa linha: **controle segmentado**
   Abertas / Concluídas / Todas, com a contagem de cada uma, e um **seletor de projeto** que filtra
   ao trocar (sem pílulas soltas). Link "gerenciar projetos". Tarefa rápida (título + projeto +
   prazo); cada linha com ▶ timer, ✓ concluir, ★ prioridade de hoje, ? explicar (IA), ✎ editar.
   Formulário de edição com status, próximo passo, descrição, tempo registrado e excluir.
3b. **Projetos** (`/projetos/`): botão "+ novo projeto" que expande o formulário (nome, cor em
   amostras, descrição); cards com borda superior na cor do projeto, descrição, barra de progresso
   (concluídas/total), a fazer · fazendo · concluídas · tempo investido, selo de atrasadas e
   próximo prazo; card "Avulsas"; seção de arquivados (restaurar/excluir).
   **Página do projeto** (`/projetos/<id>`): tiles (progresso, total, a fazer, fazendo, concluídas,
   atrasadas, tempo), tarefas abertas com "+ tarefa neste projeto", concluídas recolhíveis,
   gráfico dos últimos 30 dias (concluídas × a fazer por dia) e "editar projeto" recolhível.
4. **Calendário** (`/calendario?mes=AAAA-MM&dia=AAAA-MM-DD`): mês de segunda a domingo; resumo
   do mês (% de hábitos cumpridos, tempo focado, tarefas concluídas, dias com journaling). Cada
   dia mostra: barra de hábitos (cumpridos/previstos, sem contar os semanais), ★ prioridade
   (verde se concluída), ✎ journaling, até 3 prazos (atrasado em vermelho, concluído riscado,
   borda na cor do projeto) e tempo focado. No celular, os prazos viram um ponto. Painel do dia:
   prioridade, prazos com ações, "+ tarefa com prazo neste dia", hábitos do dia, sessões do
   timer, concluídas, journaling e link para o fechamento daquele dia.
4b. **Evolução** (`/evolucao?dias=7|14|30|90`): tiles (% hábitos cumpridos, dias com todos os
   hábitos, tarefas concluídas, a fazer início → hoje, tempo focado) e quatro gráficos:
   **hábitos cumpridos por dia** (barras empilhadas feito + mínimo sobre uma trilha de previstos;
   semanais fora da conta diária), **tarefas por dia** (barras agrupadas: concluídas no dia × a
   fazer no fim do dia), **minutos focados por dia** (barra simples + linha de meta do flow) e
   **cumprimento por hábito** (barras horizontais em %, mínimo conta).
   Seção "Mais detalhes":
   **tarefas criadas × concluídas por dia** (barras agrupadas + frase com o saldo: a fila cresce
   ou diminui), **esta semana × semana anterior** (halteres por hábito: bolinha cinza = 7 dias
   anteriores, verde = últimos 7, com a diferença em pontos percentuais), **tempo por projeto**
   (barras horizontais na cor do projeto, parte escura = tempo focado; avulsas incluídas) e **um
   gráfico por hábito numérico** (valor por dia; linha da meta ou, sem meta, da média).
5. **Garagem** (`/garagem/`): aviso de congelamento; captura com etiqueta; filtro;
   "virar tarefa" (com projeto) e "descartar".
6. **Fechamento** (`/fechamento?data=`): 1) registros dos hábitos marcados "no fechamento"
   (números e rádio não/mínimo/feito); 2) journaling; 3) prioridade de amanhã + primeiro passo;
   situação dos automáticos; navegação para o dia anterior. Salvar grava tudo de uma vez.
7. **Ajustes** (`/ajustes`): somente leitura (config, IA, chave presente/ausente, estatísticas
   da memória da IA), botões "testar conexão" e "limpar memória".

### Gráficos (regras)

- SVG gerado no servidor (`graficos.py`), sem biblioteca nem CDN. Um eixo só, grade fina discreta.
- Barras de no máximo 24px, ponta arredondada de 4px e base reta, 2px de folga entre segmentos
  empilhados e entre barras vizinhas.
- Cores validadas contra o fundo escuro (faixa de luminosidade e daltonismo): feito/concluídas
  `#2fae78`, mínimo `#8a7fd8` (o mesmo roxo usado para "mínimo" em todo o app), a fazer e
  valores numéricos `#5b8fe0`, criadas `#c0873a`, contexto/semana anterior cinza `#6b7385`.
- Linha de meta/média com o rótulo na margem direita do gráfico (nunca em cima das barras).
- Legenda com amostra sempre que houver 2+ séries; texto nunca na cor da série.
- Cada dia tem uma área de hover/toque/foco maior que a barra, com tooltip. Cada gráfico tem
  "ver tabela" com os números. No celular, o gráfico rola dentro do próprio quadro.

---

## 6. IA (opcional, somente leitura)

- **Desligada por padrão.** Desligada, os botões somem e nada quebra.
- Provedores: `azure_openai` (URL `{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=…`,
  header `api-key`; se o endpoint contiver `/openai/v1`, usar `{endpoint}/chat/completions` com
  `model`) e `openai_compativel` (Bearer). Enviar só `messages` (+ `model` quando for o caso),
  sem temperature/max_tokens, para funcionar com qualquer modelo.
- Chave em `.env` (`AZURE_OPENAI_API_KEY` ou `IA_API_KEY`). A chave nunca vai para o
  navegador nem para o log.
- **Nenhuma rota de IA grava tarefas ou hábitos.** A UI rotula a resposta como sugestão.
- Funções:
  - **Explicar tarefa**: O que é / Passos (3–6 microtarefas) / Comece agora (10 min).
  - **O que faço primeiro?**: Agora / Depois (blocos de horário a partir da hora atual) / Pode esperar.
  - **Pergunta livre** sobre tarefas e cronograma, com o contexto do dia.
  - **Como foi minha semana?**: O que foi bem / O que caiu / Um ajuste. Journaling só entra
    com `enviar_journaling: true`.
- Prompt de sistema: os princípios da seção 1, "use só os dados fornecidos", "não diga que
  criou ou alterou nada", até cerca de 200 palavras, negrito + listas com "- ".
- Log de cada chamada, sem conteúdo, em `dados/ia_log.jsonl` (quando, função, ok, segundos, uso, erro).

### Memória (cache) — não gastar tokens à toa

- Toda chamada passa por `responder()`: calcula a **chave = sha256(função + prompt de sistema
  + contexto estável + instrução + partes da chave)**. Se houver `resposta_ia` válida
  (idade < `cache_dias`, padrão 30), devolve a guardada sem chamar o provedor e soma `usos`.
- Partes da chave: **explicar** usa só o conteúdo da tarefa (título, projeto, prazo, próximo
  passo, descrição), então vale entre dias. **Primeiro/livre** usam dia + período (manhã <12h,
  tarde <18h, noite). **Semana** usa o dia.
- O contexto é estável de propósito: o tempo investido é arredondado para 15 min e só aparece a
  partir de 15 min, e as sessões em andamento não entram na contagem. Assim, um timer rodando
  não invalida o cache a cada minuto.
- A hora exata vai **no fim** da mensagem do usuário e fica fora da chave. Sistema e contexto
  vêm primeiro, o que também aproveita o cache de prompt do provedor.
- `GET /ia/memoria?modo=…` **só consulta** o cache. A tela Hoje usa essa rota ao abrir para
  mostrar a última resposta válida sem chamar a IA.
- A resposta traz `cache` e `criada_em`. A UI mostra "da memória · gerada em … · sem gastar
  tokens" ou "gerada agora", e um link **refazer** (`{"refazer": true}` força nova chamada e
  substitui a entrada).
- Entradas vencidas são apagadas ao gravar uma nova. Ajustes mostra respostas guardadas, vezes
  reaproveitadas e tokens poupados (tokens × usos). Tem botão "limpar memória".

---

## 7. Segurança (app local sem login)

- POST com `Origin`/`Referer` de outro host → 403.
- Redirecionamentos `next` aceitam só caminhos locais (`/…`, nunca `//…`).
- Todo texto escapado no Jinja. A IA é renderizada por um markdown mínimo que escapa antes de formatar.
- Validar entradas: tipos e frequências por lista fechada, números com vírgula ou ponto, datas ISO.
  Não aceitar registro de hábito no futuro.
- `host` padrão `127.0.0.1`. O `CONFIG.md` avisa que `0.0.0.0` expõe o app sem login.

---

## 8. Estrutura

```
app.py  config.json  CONFIG.md  README.md  PROMPT.md  requirements.txt  .env.example  iniciar.bat
dados/                  rotina.db, ia_log.jsonl (criados em runtime)
rotina/
  __init__.py           criar_app(), semente dos hábitos, proteção de origem, filtros Jinja
  configuracao.py       config + fuso + formatação pt-BR
  modelos.py            tabelas
  servicos.py           regras: níveis, sequências, grade, calendário, timer, parâmetros
  ia.py                 contexto, prompts, chamada, cache
  estatisticas.py       séries por dia (hábitos, tarefas, foco) e resumo de projetos
  graficos.py           barras SVG (simples, empilhadas, agrupadas)
  rotas_hoje.py  rotas_habitos.py  rotas_tarefas.py  rotas_projetos.py  rotas_calendario.py
  rotas_evolucao.py  rotas_garagem.py  rotas_ia.py
  templates/            base, _macros, hoje, habitos, habito_form, tarefas, tarefa_form,
                        calendario, garagem, fechamento, ajustes
  static/               estilo.css, app.js
tests/test_rotina.py
```

---

## 9. Testes (pytest) — critérios de aceitação

Banco temporário por teste (`criar_app({"SQLALCHEMY_DATABASE_URI": …, "SEMEAR": False})`). Cobrir:

- Sequência diária (hoje não quebra), dias específicos (dia livre não quebra), semanal.
- `nivel_por_valor` nas duas direções, incluindo a fase de medição.
- Grade com 12×7 e os estados corretos.
- Timer único pela regra e pelo **índice do banco** (IntegrityError ao inserir dois ativos).
- Parar grava o próximo passo e alimenta o flow. Concluir a prioridade alimenta `auto_prioridade`.
- Fechamento grava números, sim/não, journaling (→ `auto_journal`) e prioridade de amanhã.
- Toggle de registro, Garagem (`app:`, promover), arquivar/reativar sem perder histórico.
- POST de outra origem → 403. Todas as telas respondem 200 com dados.
- IA desligada → erro amigável. Azure: URL e header corretos, chave nunca na resposta.
  Journaling fora do contexto por padrão.
- **Cache:** reabrir = 0 chamadas; refazer = nova chamada; mudar tarefa/contexto = nova chamada;
  `/ia/memoria` nunca chama; timer rodando alguns minutos não invalida.
- Calendário: meses válidos e inválidos, dia futuro, prazo aparece no dia certo.
- Projetos: criar/editar/arquivar/excluir (tarefas viram avulsas), números do resumo corretos.
- Evolução: séries por dia (feito/mínimo, concluídas/a fazer), todos os períodos, texto escapado no SVG,
  comparação de semanas, tempo por projeto (avulsas incluídas), série numérica com dias sem registro.
- Migração: banco antigo sem `projeto.descricao` recebe a coluna sem perder dados.

Depois dos testes, abrir todas as telas num navegador headless (desktop e 390 px): zero erros
de JS e `scrollWidth` igual à largura da tela.

---

## 10. Ordem de entrega

Cada etapa funciona e é testada antes da seguinte:

1. Estrutura, config, modelos, semente, `iniciar.bat`
2. Regras (níveis, sequências, timer único) + testes
3. Hoje, Hábitos, Tarefas/Projetos, Garagem, Fechamento, Ajustes
4. Calendário, Projetos, Evolução (gráficos)
5. IA + memória (cache)
6. README, CONFIG, verificação visual, zip

---

## 11. Fora do escopo (não implementar sem o usuário escolher na Garagem)

Login e multiusuário, sincronização/nuvem, PWA/offline mobile, Outlook/Google Agenda, kanban,
notificações, gamificação, IA que cria ou altera dados,
arrastar e soltar no calendário, anexos, temas.

**Regra de processo:** depois da v1 em uso, nenhuma funcionalidade entra por 14 dias. Ideias vão
para a Garagem com `app:`. Na revisão, escolher **uma**, e só se ainda fizer falta depois de uso real.
Se o sistema não estiver sendo usado, a resposta não é adicionar funcionalidade.
