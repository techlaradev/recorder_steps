# 🐞 Test Plan Orchestrator

> **From Steps to Automation**
>
> Plataforma de orquestração de testes baseada em IA que transforma fluxos executados em cenários, BDDs e automações Playwright, acelerando a criação, manutenção e execução de testes.

---

# 🎯 Objetivo

O **Test Plan Orchestrator** foi criado para reduzir o esforço manual necessário para transformar uma ideia, fluxo ou execução manual em um ativo automatizado pronto para execução.

A plataforma atua como uma camada de orquestração entre:

```text
Fluxo executado
        ↓
Cenários de teste
        ↓
BDD (Gherkin)
        ↓
Playwright
        ↓
Execução
        ↓
Evidências
```

---

# 🚀 Funcionalidades

## 🎥 Recorder de Steps

Captura ações realizadas pelo usuário para posterior processamento.

### Benefícios

- Redução de escrita manual
- Rastreabilidade
- Reaproveitamento de fluxos

---

## 🤖 Geração de Cenários

Transforma os passos gravados em cenários estruturados.

Exemplo:

```text
Dado que o usuário acessa a tela de login
Quando informa credenciais válidas
Então deve visualizar a página inicial
```

---

## 📝 Geração de BDD

Conversão automática de cenários em Gherkin.

Exemplo:

```gherkin
Feature: Login

Scenario: Login com sucesso

    Given que o usuário está na tela de login
    When informa credenciais válidas
    Then deve ser autenticado com sucesso
```

---

## 🎭 Transformação para Playwright

Conversão automática de BDDs em automações Playwright.

### Padrões

- pytest
- Page Fixture
- Assertions
- Screenshots obrigatórias
- Estrutura padronizada

---

## 📸 Evidências

Geração automática de screenshots durante a execução.

Objetivos:

- Auditoria
- Rastreabilidade
- Apoio à análise de falhas

---

## ⚙️ Execução Centralizada

Runner responsável por:

```text
Executar cenários
Executar automações
Coletar resultados
Gerar relatórios
```

---

## 🧠 Integração com IA Local

Suporte a modelos executados via Ollama.

Modelo padrão:

```text
qwen2.5-coder:14b
```

---

# 🏗️ Arquitetura

```text
main.py

├── flows/
│
├── ia_prompting/
│   ├── code_perform_IA.py
│   └── prompts/
│
└── orchestrator_flows/
    │
    ├── domain/
    │   ├── execution.py
    │   └── scenario.py
    │
    ├── services/
    │   ├── bdd_service.py
    │   ├── orchestrator.py
    │   ├── printer_service.py
    │   ├── recorder_service.py
    │   └── scenario_transformer_service.py
    │
    ├── tools/
    │   ├── evidence-responses-gen.py
    │   └── folder-gen.py
    │
    └── utils/
        └── slugify.py
```

---

# 🔄 Fluxo Principal

```text
Recorder
    ↓
Scenario Generator
    ↓
BDD Generator
    ↓
Playwright Transformer
    ↓
Execution Runner
    ↓
Evidence Generator
```

---

# 📂 Estrutura de Saída

```text
flows/
└── test-plans/
    └── flow-name/
        ├── scenarios/
        ├── flow.feature
        ├── automation.py
        └── evidences/
```

---

# 🧩 Componentes

## Domain

Responsável pelos objetos centrais da aplicação.

```text
execution.py
scenario.py
```

---

## Services

Responsável pelas regras de negócio e orquestração.

```text
bdd_service.py

recorder_service.py

scenario_transformer_service.py

printer_service.py

orchestrator.py
```

---

## Tools

Ferramentas auxiliares utilizadas pela plataforma.

```text
folder-gen.py

evidence-responses-gen.py
```

---

## Utils

Utilitários reutilizáveis.

```text
slugify.py
```

---

# ⚡ Instalação

## Criar ambiente virtual

```bash
python -m venv .venv
```

---

## Ativar ambiente

Windows:

```bash
.\.venv\Scripts\activate
```

Linux:

```bash
source .venv/bin/activate
```

---

## Instalar dependências

```bash
pip install -r requirements.txt
```

---

# 🎭 Playwright

Instalar navegadores:

```bash
playwright install
```

---

# 🧠 Ollama

Verificar se o Ollama está ativo:

```bash
netstat -ano | findstr 11434
```

Iniciar:

```bash
ollama serve
```

Baixar modelo:

```bash
ollama pull qwen2.5-coder:14b
```

---

# ▶️ Executar Projeto

```bash
python main.py
```

---

# 📋 Requisitos

- Python 3.10+
- Playwright
- Ollama
- Pytest

---

# 🎯 Filosofia do Projeto

O foco do projeto não é apenas gerar código.

O objetivo é permitir que usuários com menor conhecimento técnico consigam transformar fluxos de teste em automações executáveis através de um processo guiado e padronizado.


---

# 🛣️ Roadmap

## ✅ Concluído

- [x] Recorder de Steps
- [x] Geração de Cenários
- [x] Geração de BDD
- [x] Transformação para Playwright
- [x] Integração com Ollama
- [x] Evidências automáticas
- [x] Estrutura de Orquestração

---

## 🚧 Em Desenvolvimento

- [ ] Ollama Service
- [ ] Execution Runner
- [ ] Coverage Runner
- [ ] Coverage HTML Report

---

## 🔮 Futuro
- [ ] Empacotamento em EXE
- [ ] Interface self-service
- [ ] Mapa de cobertura funcional

---

# 💜 Autor

Desenvolvido para acelerar a criação de automações através da combinação de:

- QA
- IA Generativa
- Playwright
- BDD
- Engenharia de Qualidade

---

> 🐞 Test Plan Orchestrator
>
> **Record. Generate. Automate.**
