---
name: mapear
description: Atualiza o CLAUDE.md com o estado atual do projeto — rotas, helpers, templates, padrões e decisões arquiteturais.
---

Você é um assistente de documentação técnica do projeto Orchestrator.

Sua tarefa é **atualizar o arquivo `CLAUDE.md`** na raiz do projeto com uma visão fiel do estado atual do código.

## Passos

1. **Leia os arquivos principais** para entender o estado atual:
   - `web_app.py` — todas as rotas (`@app.route`), helpers (`def _...`), padrões subprocess
   - `templates/` — liste todos os templates existentes e o que cada um renderiza
   - `scripts/bdd_generator.py` — pipeline do BDD watcher
   - `flows/` — estrutura de pastas existentes (sem ler o conteúdo dos .py)

2. **Identifique as decisões arquiteturais relevantes**:
   - Flags de pipeline (ready-bdd.flag, ready-for-testing.flag, etc.)
   - Padrões de subprocess (encoding, capture_output, cwd)
   - Configurações do Flask (use_reloader, debug, port)
   - Padrões de UI nos templates (CSS tokens, polling, acordeões)

3. **Atualize o `CLAUDE.md`** mantendo as seções existentes mas corrigindo qualquer informação desatualizada:
   - Estrutura de arquivos (adicionar/remover entradas)
   - Tabela de helpers (função → descrição)
   - Tabela de rotas (rota → descrição)
   - Decisões arquiteturais (adicionar novas, corrigir antigas)
   - Como rodar o projeto

4. **Não apague** seções que ainda são válidas — apenas corrija ou complemente.

5. Ao final, confirme quais seções foram atualizadas e o que mudou em relação à versão anterior.
