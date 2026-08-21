"""
bdd_generator.py — Gerador de BDD automático (watcher independente)

Monitora a pasta flows/ em busca de arquivos ready-bdd.flag criados após
a limpeza do código. Comportamento por modo:

  SINGLE: um flag por cenário → gera um .feature individual via stdout
  SUITE:  múltiplos flags por bateria → gera UMA feature consolidada com
          todos os cenários limpos da bateria (igual a _safe_bdd_suite)

Pipeline completo:
  gravação → [cleaner] → ready-bdd.flag → [bdd_generator] → ready-for-testing.flag

Uso:
  python bdd_generator.py
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

FLOWS_DIR  = Path(__file__).parent.parent / "flows"
POLL_SECS  = 3
TIMEOUT_SINGLE = 120   # segundos — cenário único
TIMEOUT_SUITE  = 240   # segundos — bateria consolidada


# ── helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _read_flag(flag_path: Path) -> dict:
    """Lê um arquivo de flag KEY=VALUE e retorna como dict."""
    data: dict[str, str] = {}
    for line in flag_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data


def _mark_failed(flag_path: Path, scenario: str, reason: str) -> None:
    flag_path.unlink(missing_ok=True)
    (flag_path.parent / "bdd-failed.flag").write_text(
        f"SCENARIO={scenario}\nREASON={reason}\n", encoding="utf-8"
    )
    print(f"[{_now()}] ❌ Erro em '{scenario}': {reason}")


# ── geração SINGLE ────────────────────────────────────────────────────────────

def _process_single(flag_path: Path) -> None:
    """Gera BDD de um cenário SINGLE a partir do ready-bdd.flag."""
    info = _read_flag(flag_path)
    scenario_name = info.get("SCENARIO", flag_path.parent.name)
    clean_path    = Path(info["CLEAN"])   if "CLEAN"   in info else None
    feature_path  = Path(info["FEATURE"]) if "FEATURE" in info else None
    raw_path      = flag_path.parent / f"{scenario_name}.py"

    print(f"\n[{_now()}] ▶ [SINGLE] Gerando BDD: {scenario_name}")

    source = None
    if clean_path and clean_path.exists():
        source = clean_path
    elif raw_path.exists():
        source = raw_path

    if not source:
        _mark_failed(flag_path, scenario_name, "Arquivo de código não encontrado.")
        return
    if not feature_path:
        _mark_failed(flag_path, scenario_name, "Caminho de feature não definido.")
        return

    code = source.read_text(encoding="utf-8")
    prompt = (
        f"The following is a Python Playwright test for the scenario '{scenario_name}'.\n\n"
        f"```python\n{code}\n```\n\n"
        f"Convert it to a Gherkin BDD Feature file.\n"
        f"Rules:\n"
        f"- Start with: Feature: {scenario_name.replace('-', ' ').title()}\n"
        f"- Include one or more Scenario: blocks\n"
        f"- Use Given/When/Then format\n"
        f"- Output ONLY the Gherkin text — no code fences, no explanations, no markdown\n"
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SINGLE,
            cwd=str(Path(__file__).parent.parent),
        )
    except subprocess.TimeoutExpired:
        _mark_failed(flag_path, scenario_name, f"Timeout ({TIMEOUT_SINGLE}s).")
        return
    except FileNotFoundError:
        _mark_failed(flag_path, scenario_name, "Claude CLI não encontrado no PATH.")
        return

    if result.returncode != 0:
        _mark_failed(flag_path, scenario_name, result.stderr or result.stdout or "erro claude CLI.")
        return

    gherkin = result.stdout.strip()
    if not gherkin or "Feature:" not in gherkin:
        _mark_failed(flag_path, scenario_name, "Claude não gerou Gherkin válido.")
        return

    feature_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.write_text(gherkin, encoding="utf-8")

    flag_path.unlink(missing_ok=True)
    (flag_path.parent / "ready-for-testing.flag").write_text(
        f"SCENARIO={scenario_name}\nFEATURE={feature_path.resolve()}\n", encoding="utf-8"
    )
    print(f"[{_now()}] ✅ Feature salva: {feature_path}")


# ── geração SUITE (consolidada por bateria) ───────────────────────────────────

def _process_suite(plan_name: str, flags: list[Path]) -> None:
    """Gera BDD consolidado de uma bateria SUITE a partir de todos os flags."""
    plan_dir      = FLOWS_DIR / "test-plans" / plan_name
    scenarios_dir = plan_dir / "scenarios"
    cleaned_dir   = plan_dir / "cleaned"
    feature_path  = plan_dir / f"{plan_name}.feature"

    print(f"\n[{_now()}] ▶ [SUITE] Gerando BDD consolidado: {plan_name} ({len(flags)} cenários)")

    # Coleta todos os cenários limpos disponíveis
    parts: list[str] = []
    for sc_dir in sorted(scenarios_dir.iterdir()) if scenarios_dir.exists() else []:
        if not sc_dir.is_dir():
            continue
        py_name = sc_dir.name.replace("-", "_")
        clean   = cleaned_dir / f"test_{py_name}.py"
        raw     = sc_dir / f"{sc_dir.name}.py"
        source  = clean if clean.exists() else (raw if raw.exists() else None)
        if source is None:
            continue
        code = source.read_text(encoding="utf-8").strip()
        if code:
            parts.append(f"SCENARIO: {sc_dir.name}\n\n```python\n{code}\n```")

    if not parts:
        for f in flags:
            _mark_failed(f, plan_name, "Nenhum cenário com código encontrado.")
        return

    combined = "\n\n---\n\n".join(parts)
    prompt = (
        f"The following are Python Playwright test scenarios from the '{plan_name}' suite.\n\n"
        f"{combined}\n\n"
        f"---\n\n"
        f"Convert ALL scenarios above into a single consolidated Gherkin BDD Feature file.\n"
        f"Rules:\n"
        f"- Start with: Feature: {plan_name.replace('-', ' ').title()}\n"
        f"- Include one Scenario: block per test scenario\n"
        f"- Use Given/When/Then format\n"
        f"- Output ONLY the Gherkin text — no code fences, no explanations, no markdown\n"
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SUITE,
            cwd=str(Path(__file__).parent.parent),
        )
    except subprocess.TimeoutExpired:
        for f in flags:
            _mark_failed(f, plan_name, f"Timeout ({TIMEOUT_SUITE}s).")
        return
    except FileNotFoundError:
        for f in flags:
            _mark_failed(f, plan_name, "Claude CLI não encontrado no PATH.")
        return

    if result.returncode != 0:
        err = result.stderr or result.stdout or "erro claude CLI."
        for f in flags:
            _mark_failed(f, plan_name, err)
        return

    gherkin = result.stdout.strip()
    if not gherkin or "Feature:" not in gherkin:
        for f in flags:
            _mark_failed(f, plan_name, "Claude não gerou Gherkin válido.")
        return

    feature_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.write_text(gherkin, encoding="utf-8")

    # Remove TODOS os ready-bdd.flag da bateria e escreve ready-for-testing no plano
    for f in flags:
        f.unlink(missing_ok=True)
    (plan_dir / "ready-for-testing.flag").write_text(
        f"PLAN={plan_name}\nFEATURE={feature_path.resolve()}\n", encoding="utf-8"
    )
    print(f"[{_now()}] ✅ Feature consolidada: {feature_path}")


# ── loop principal ─────────────────────────────────────────────────────────────

def main() -> None:
    print("╔══════════════════════════════════════════════╗")
    print("║      BDD Generator  |  Claude CLI           ║")
    print("║  Monitorando flows/ por ready-bdd.flag...   ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    if not FLOWS_DIR.exists():
        print(f"[AVISO] Pasta flows/ não encontrada. Aguardando criação...")

    while True:
        all_flags = list(FLOWS_DIR.rglob("ready-bdd.flag")) if FLOWS_DIR.exists() else []

        if all_flags:
            # Agrupa por MODE e PLAN para não processar SUITE múltiplas vezes
            single_flags: list[Path] = []
            suite_plans:  dict[str, list[Path]] = {}

            for flag_path in all_flags:
                try:
                    info = _read_flag(flag_path)
                    mode = info.get("MODE", "SINGLE").upper()
                    if mode == "SUITE":
                        plan = info.get("PLAN", flag_path.parent.parent.parent.name)
                        suite_plans.setdefault(plan, []).append(flag_path)
                    else:
                        single_flags.append(flag_path)
                except Exception as exc:
                    print(f"[{_now()}] ⚠️ Erro ao ler flag {flag_path}: {exc}")

            for flag_path in single_flags:
                try:
                    _process_single(flag_path)
                except Exception as exc:
                    print(f"[{_now()}] ❌ Erro inesperado (SINGLE): {exc}")
                    flag_path.unlink(missing_ok=True)

            for plan_name, flags in suite_plans.items():
                try:
                    _process_suite(plan_name, flags)
                except Exception as exc:
                    print(f"[{_now()}] ❌ Erro inesperado (SUITE {plan_name}): {exc}")
                    for f in flags:
                        f.unlink(missing_ok=True)

        time.sleep(POLL_SECS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBDD Generator encerrado.")
        sys.exit(0)
