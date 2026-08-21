# orchestrator_flows/ — Domínio e serviços

> Camada de domínio do Orchestrator. Contém modelos, serviços e integrações de IA.

---

## Modelo central: `Scenario`

`domain/scenario.py` — dataclass que representa um cenário de teste.

```python
Scenario(name="login-usuario", url="https://...", mode=ExecutionMode.SINGLE)
Scenario(name="checkout", url="...", mode=ExecutionMode.SUITE, plan_name="compras-suite")
```

Propriedades calculadas — **não construa paths manualmente, use estas**:

| Propriedade | SINGLE | SUITE |
|---|---|---|
| `raw_path` | `flows/unity-test/<nome>/<nome>.py` | `flows/test-plans/<plano>/scenarios/<nome>/<nome>.py` |
| `clean_path` | `flows/unity-test/<nome>/test_<nome>.py` | `flows/test-plans/<plano>/cleaned/test_<nome>.py` |
| `feature_path` | `flows/unity-test/<nome>/<nome>.feature` | `flows/test-plans/<plano>/<plano>.feature` |
| `evidences_dir` | `flows/unity-test/<nome>/evidences/` | `flows/test-plans/<plano>/evidences/<nome>/` |

Sempre chame `scenario.ensure_dirs()` antes de escrever arquivos.

---

## ExecutionMode

```python
class ExecutionMode(Enum):
    SINGLE     = "single"      # cenário unitário
    SUITE      = "suite"       # cenário dentro de uma bateria
    REPROCESS  = "reprocess"   # reprocessar sem regravar
    REGRESSION = "regression"  # executar bateria completa
```

---

## Serviços

| Arquivo | Responsabilidade |
|---|---|
| `services/scenario_transformer_service.py` | Orquestra a limpeza do código via IA |
| `ia_prompting/code_perform_IA.py` | `StepTransformer` — monta o prompt de transformação |
| `ia_prompting/prompts/transform_playwright.py` | Template do prompt de limpeza |
| `flow_design/client_claude.py` | `ClaudeClient` — wrapper do Anthropic SDK |
| `flow_design/client_ollama.py` | Cliente Ollama (alternativa local, não usado no fluxo principal) |
| `services/recorder_service.py` | Dispara o Playwright Codegen |
| `services/humanintervention.py` | Pausa a gravação para intervenção manual |

---

## Regras ao estender o domínio

- Novos tipos de cenário → adicionar em `ExecutionMode` e atualizar propriedades de `Scenario`
- Novos paths de arquivo → adicionar como `@property` em `Scenario`, nunca hardcodar em `web_app.py`
- Novos serviços de IA → seguir o padrão de `StepTransformer` (classe com método `transform`)
