@echo off
chcp 65001 >nul
title Orchestrator Cleaner — aguardando gravações

echo ╔══════════════════════════════════════════════╗
echo ║     Orchestrator Cleaner  ^|  Claude CLI      ║
echo ║  Monitorando pasta flows\ por flags...       ║
echo ╚══════════════════════════════════════════════╝
echo.

:loop
REM ── Varre TODOS os subdiretórios de flows\ em busca de flags ──────────────
FOR /R "flows" %%F IN (ready-for-clean.flag) DO (
    IF EXIST "%%F" (
        CALL :process "%%F"
    )
)
timeout /t 3 /nobreak >nul
GOTO loop

REM ═════════════════════════════════════════════════════════════════════════
:process
SET FLAG_FILE=%~1
SET FLAG_DIR=%~dp1

REM Lê os caminhos do flag (formato KEY=VALUE)
FOR /F "tokens=1,* delims==" %%K IN (%FLAG_FILE%) DO (
    IF "%%K"=="RAW"      SET RAW_PATH=%%L
    IF "%%K"=="CLEAN"    SET CLEAN_PATH=%%L
    IF "%%K"=="SCENARIO" SET SCENARIO=%%L
)

echo [%TIME%] ▶ Limpando cenário: %SCENARIO%
echo          RAW:   %RAW_PATH%
echo          CLEAN: %CLEAN_PATH%

REM ── Prompt enviado ao Claude CLI ─────────────────────────────────────────
SET PROMPT=Você é um QA Engineer especializado em Playwright Python e pytest-playwright.^

Leia o arquivo %RAW_PATH% e transforme-o em um teste pytest limpo seguindo TODAS as regras abaixo.^

^

REGRAS OBRIGATÓRIAS:^

- Use APENAS playwright.sync_api (nunca async/await)^

- Assinatura exata: def test_%SCENARIO%(page: Page):^

- Importe no topo: from playwright.sync_api import Page, expect^

- Screenshots obrigatórias nos checkpoints de negócio usando _EVIDENCES:^

    from pathlib import Path as _Path^

    _EVIDENCES = _Path(__file__).parent / "evidences"^

    _EVIDENCES.mkdir(exist_ok=True)^

- Para CAPTCHA/MFA/OTP use: HumanIntervention.required(page, reason="...")^

  com: from orchestrator_flows.services.humanintervention import HumanIntervention^

- NUNCA invente seletores, textos ou URLs que não existam no script original^

- Prefira seletores: get_by_test_id(), get_by_role()^

- Retorne SOMENTE código Python, sem explicações^

^

Salve o resultado em: %CLEAN_PATH%^

Crie os diretórios pai se necessário.

claude -p "%PROMPT%" --allowedTools "Read,Write,Edit"

IF %ERRORLEVEL% EQU 0 (
    echo [%TIME%] ✅ %SCENARIO% limpo com sucesso.
) ELSE (
    echo [%TIME%] ❌ Erro ao limpar %SCENARIO%. Código: %ERRORLEVEL%
)

DEL "%FLAG_FILE%"
GOTO :EOF
