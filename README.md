# Rotina

Rastreador de hábitos com tarefas em volta. Roda 100% local, sem login e sem nuvem.
A IA é opcional e só funciona se você ligar.

## Rodar (Windows)

```bat
cd rotina
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abra **http://127.0.0.1:5001**. Ou dê dois cliques em `iniciar.bat`, que faz tudo isso sozinho.

O banco fica em `dados/rotina.db` e é criado na primeira execução, já com os 8 hábitos
iniciais. Para fazer backup, copie esse arquivo.

## Uso diário

| Quando | Onde | O quê |
|---|---|---|
| Manhã | **Hoje** | Ver a ★ prioridade, dar ▶ no timer e marcar os hábitos que já couberem |
| Durante o dia | campo 💡 no topo (tecla `/`) | Apareceu uma ideia? Estaciona e volta ao que estava fazendo |
| Ao parar o timer | janela de parar | "Foi focado?" e "qual o próximo passo?" |
| Ver progresso | **Evolução** / **Projetos** | Gráficos por dia (7 a 90 dias) e números de cada projeto |
| Planejar a semana | **Calendário** | Prazos, ★ e constância dos hábitos no mês; clique no dia para detalhe e “+ tarefa neste dia” |
| Noite (2 min) | **Fechamento** | Números do celular, checks que faltam, uma linha de journaling, ★ de amanhã |

## Como cada hábito é contado

| Hábito | Tipo | Conta como feito |
|---|---|---|
| Redes sociais | número, limite | Fase de medição (sem meta): registrar já conta. Depois de 1 semana, defina a meta |
| Checagens do celular | número, limite | Mesma coisa, em desbloqueios |
| Leitura | número | 10 páginas = feito, 2 = mínimo |
| Concluir a prioridade do dia | automático | Concluir a tarefa ★ do dia. Trabalhar nela no timer = mínimo |
| Estado de flow | automático | 60 min em sessões marcadas como focadas. Uma sessão focada de 25 min = mínimo |
| Ambiente organizado | sim/não | Mínimo: arrumar a cama |
| Desacelerar à noite | sim/não, seg a sex | Ajuste os dias em Hábitos → editar |
| Journaling | automático | Salvar um texto no fechamento |

**Mínimo e feito mantêm a sequência.** O dia de hoje nunca quebra a sequência antes de acabar.
Arquivar um hábito guarda todo o histórico. Ao reativar, a melhor sequência continua lá.

## IA com memória

A IA só é chamada quando o contexto muda (tarefas, hábitos, dia ou período do dia). Reabrir a
mesma pergunta, ou a tela Hoje, mostra a resposta guardada sem gastar tokens (“da memória”).
“refazer” força uma nova. Detalhes em CONFIG.md.

## Regra do projeto: 14 dias sem funcionalidade nova

Depois de começar a usar, nenhuma funcionalidade nova entra por 14 dias. Ideia para o próprio
sistema vai para a Garagem com o prefixo `app:`, por exemplo `app: gráfico mensal`.
A Garagem mostra a data de liberação. Nesse dia, escolha **uma** ideia, e só se ela ainda
fizer falta.

## Testes

```bat
pip install pytest
python -m pytest
```

## Estrutura

```
app.py               ponto de entrada (porta 5001)
config.json          configuração (explicada em CONFIG.md)
PROMPT.md            especificação completa (para recriar/evoluir com IA)
.env                 chave da IA (copie de .env.example)
rotina/
  configuracao.py    config, fuso horário, formatação de datas pt-BR
  modelos.py         tabelas SQLite
  servicos.py        regras: sequências, hábitos automáticos, timer único
  ia.py              contexto e chamada da IA (somente leitura)
  estatisticas.py    séries por dia e resumo de projetos
  graficos.py        gráficos de barras em SVG (sem bibliotecas)
  rotas_*.py         telas: hoje/fechamento/ajustes, hábitos, tarefas+timer, projetos, calendário, evolução, garagem, ia
  templates/, static/
tests/               pytest
```

O timer único é garantido também no banco, por um índice único parcial. Não existe como
ter duas sessões rodando ao mesmo tempo.

## Licença

[MIT](LICENSE)
