# ⚜️ Orchestrator — Regras críticas

> Leia **sempre** antes de tocar no código. São as decisões que custaram bugs para descobrir.
>
> 📋 Regras de negócio (pipeline, SUITE vs SINGLE, falhas, reprocessamento): veja **`REGRAS.md`**

---

## Como rodar

```bash
python web_app.py                   # Flask (porta 5000)
python scripts/bdd_generator.py     # BDD watcher — rode em paralelo
```

---

## Regras que não podem ser quebradas

### 1. `use_reloader=False` é obrigatório
O Werkzeug auto-reloader reinicia o processo quando o Claude CLI escreve em `flows/`,
matando o job em andamento e apagando o resultado da memória.

```python
app.run(debug=True, use_reloader=False, port=5000)
```

### 2. Subprocess do Claude sempre com `encoding="utf-8"`
No Windows, `text=True` sem encoding usa `cp1252`. Acentos ficam corrompidos (`válidas` → `vÃ¡lidas`).

```python
subprocess.run(["claude", "-p", prompt],
               capture_output=True, text=True, encoding="utf-8", ...)
```

### 3. BDD via stdout — nunca via Write tool
Claude imprime o Gherkin no stdout; Python lê e salva. Não peça ao Claude para usar a Write tool.

```python
gherkin = result.stdout.strip()
scenario.feature_path.write_text(gherkin, encoding="utf-8")
```

### 4. `results_by_job` renderiza direto — sem redirect
Redirect entre `pop(job_id)` e a renderização perde o resultado se o servidor reiniciar entre as duas requests.

### 5. `bdd_generator.py` usa `Path(__file__).parent.parent`
O script fica em `scripts/` — `.parent` sozinho resolve para `scripts/flows/` (não existe).

---

## Convenções de nomenclatura

| Tipo | Padrão |
|---|---|
| Gravação raw | `<nome>.py` |
| Código limpo | `test_<nome_com_underscore>.py` |
| Feature BDD | `<nome>.feature` |
| Flags de pipeline | `ready-bdd.flag`, `ready-for-testing.flag`, `transform-failed.flag`, `bdd-failed.flag` |

Flags são texto `KEY=VALUE`, uma por linha.
