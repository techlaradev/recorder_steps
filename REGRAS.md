# 📋 Regras de Negócio — Orchestrator

> Comportamentos intencionais do sistema. Antes de implementar uma feature, verifique se ela respeita estas regras.

---

## Pipeline — Progressão de estado

Um cenário **só avança** para a próxima etapa se a anterior estiver completa:

```
❶ Gravação     → existe <nome>.py
       ↓
❷ Limpeza      → existe test_<nome>.py     (Claude CLI transforma o raw)
       ↓
❸ BDD          → existe <nome>.feature     (Claude CLI gera o Gherkin)
       ↓
❹ Execução     → pytest roda test_<nome>.py
       ↓
❺ Evidências   → screenshots em evidences/
```

Regras de progressão:
- **Não processa** sem gravação (`<nome>.py` inexistente → não aparece na fila)
- **Não executa** sem código limpo (`test_<nome>.py` inexistente → pytest não roda raw)
- **Não aparece em "Executar"** sem código limpo
- BDD pode existir ou não — não bloqueia execução

---

## SINGLE vs SUITE

### SINGLE — cenário unitário
- 1 gravação → 1 limpeza → 1 BDD → 1 execução
- Feature BDD: 1 arquivo com 1 cenário
- Paths: `flows/unity-test/<nome>/`

### SUITE — bateria de cenários
- N gravações → N limpezas → **1 BDD consolidado** → 1 regressão
- Feature BDD: **1 arquivo único** com todos os cenários da bateria
- O BDD consolidado **só é gerado quando 100% dos cenários estiverem limpos**
- Paths: `flows/test-plans/<plano>/`

---

## Falhas — comportamento isolado

- Falha na limpeza de 1 cenário SUITE **não trava** os outros — cada um é processado de forma independente
- O flag `transform-failed.flag` é informativo (registra o erro) mas não bloqueia o watcher
- Falha no BDD também é isolada — escreve `bdd-failed.flag` e segue em frente
- O resultado da bateria mostra ✅/❌ por cenário individualmente

---

## Reprocessamento

- Um cenário SUITE **pode ser reprocessado individualmente**, sem precisar reprocessar a bateria inteira
- O botão "Processar" na aba Regressão roda apenas os cenários que **ainda não têm** `test_*.py`
- Reprocessar não apaga evidências antigas

---

## BDD — geração e validade

- BDD SUITE só é gerado **depois** que todos os cenários da bateria estiverem limpos
- O Gherkin gerado deve conter `Feature:` — se não tiver, é considerado inválido e o erro é registrado
- BDD não é pré-requisito para execução — pode executar sem `.feature`
- Um `.feature` corrompido (mojibake) pode ser corrigido com: `text.encode('latin-1').decode('utf-8')`

---

## Visibilidade na UI

| Tela | Aparece quando |
|---|---|
| Aba "Executar" | Cenário tem `test_<nome>.py` |
| Aba "Regressão" | Bateria tem ao menos 1 `test_*.py` |
| Badge `📄 BDD` | `.feature` existe |
| Badge `📸 N` | Pasta `evidences/` tem screenshots |
| Botão "Gerar BDD" na batch_result | BDD **ainda não existe** para o plano |
| Botão "Regenerar BDD" | BDD **já existe** (permite atualizar) |
