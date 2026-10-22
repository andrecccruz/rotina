# config.json — campos

Depois de editar, reinicie o `python app.py`.

| Campo | Padrão | O que faz |
|---|---|---|
| `nome_app` | `Rotina` | Nome no topo e na aba |
| `porta` | `5001` | Porta local |
| `host` | `127.0.0.1` | Só este computador acessa. Use `0.0.0.0` para abrir na rede interna (não há login) |
| `fuso_horario` | `America/Sao_Paulo` | Define o que é "hoje" e a hora no timer |
| `dias_congelamento_funcionalidades` | `14` | Dias sem funcionalidade nova, contados a partir do primeiro uso |

## `ia`

| Campo | Padrão | O que faz |
|---|---|---|
| `ativa` | `false` | Liga a IA. Desligada, os botões somem e nada quebra |
| `provedor` | `azure_openai` | `azure_openai` ou `openai_compativel` |
| `endpoint` | — | Azure: `https://SEU-RECURSO.openai.azure.com`. Se o seu endpoint já termina em `/openai/v1`, o app usa o formato novo da Azure |
| `deployment` | — | Nome do deployment na Azure |
| `api_version` | `2024-10-21` | Versão da API da Azure OpenAI |
| `modelo` | `""` | Só para `openai_compativel` ou `/openai/v1` (se vazio, usa `deployment`) |
| `timeout_segundos` | `60` | Tempo máximo de espera da resposta |
| `cache` | `true` | Memória da IA: reaproveita respostas quando o contexto não mudou |
| `cache_dias` | `30` | Validade máxima de uma resposta guardada |
| `enviar_journaling` | `false` | Se `true`, o "Como foi minha semana?" envia também o journaling dos últimos 7 dias |

## `.env`

```
AZURE_OPENAI_API_KEY=sua-chave      # provedor azure_openai
IA_API_KEY=sua-chave                # provedor openai_compativel
```

A chave nunca é gravada no `config.json` e nunca vai para o navegador.

## O que a IA recebe

- Tarefas abertas: título, projeto, prazo, próximo passo e tempo investido
- Hábitos de hoje: situação e sequência
- Somente em "Como foi minha semana?": marcações dos últimos 7 dias, números (redes, páginas etc.), totais do timer e tarefas concluídas
- Journaling: só se `enviar_journaling = true`

## Memória (cache)

Cada resposta é guardada em `dados/rotina.db` (tabela `resposta_ia`) com uma chave calculada
a partir do que seria enviado. Se nada mudou, a resposta guardada é mostrada e o provedor não é chamado.

- **Explicar tarefa:** vale enquanto título, descrição, projeto, prazo ou próximo passo não mudarem (entre dias também).
- **O que faço primeiro / pergunta livre:** valem no mesmo dia e período (manhã, tarde, noite) com as mesmas tarefas e hábitos.
- **Como foi minha semana:** vale no mesmo dia com os mesmos registros.
- Timer rodando não invalida: o tempo entra arredondado a cada 15 min.
- “refazer” força uma resposta nova. “limpar memória” em Ajustes apaga tudo.

A IA só lê e sugere. Nenhuma rota de IA grava tarefas ou hábitos (só a própria memória).
Cada chamada é registrada, sem o conteúdo, em `dados/ia_log.jsonl`.
