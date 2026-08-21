import json
import re as _re
import subprocess
import sys
import threading
import time as _time
import uuid as _uuid
from pathlib import Path
from urllib.parse import quote as _url_quote

# Carrega variáveis do .env se existir (sem dependência de python-dotenv)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    import os as _os_env
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _os_env.environ.setdefault(_k.strip(), _v.strip())

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for

from orchestrator_flows.domain.execution import ExecutionMode
from orchestrator_flows.domain.scenario import Scenario
from orchestrator_flows.flow_design.client_claude import ClaudeClient
from orchestrator_flows.ia_prompting.code_perform_IA import StepTransformer
from orchestrator_flows.services.scenario_transformer_service import (
    ScenarioTransformerService,
)

import os as _os
app = Flask(__name__)


def _load_secret_key() -> bytes:
    """Retorna a chave de sessão — persistente entre restartes."""
    env_key = _os.environ.get("ORCHESTRATOR_SECRET")
    if env_key:
        return env_key.encode()
    key_file = Path(".secret_key")
    if key_file.exists():
        return key_file.read_bytes()
    key = _os.urandom(32)
    key_file.write_bytes(key)
    return key


app.secret_key = _load_secret_key()


def _pending_processing() -> dict:
    """Retorna cenários SINGLE e planos SUITE que têm gravação mas ainda não foram processados."""
    # SINGLE: raw existe, test_*.py NÃO existe
    single = []
    base_single = Path("flows") / "unity-test"
    if base_single.exists():
        for d in sorted(base_single.iterdir()):
            if not d.is_dir():
                continue
            raw = d / f"{d.name}.py"
            if not raw.exists():
                continue
            py_name  = d.name.replace("-", "_")
            test_file = d / f"test_{py_name}.py"
            if not test_file.exists():
                single.append({"name": d.name})

    # SUITE: planos com pelo menos 1 cenário sem cleaned/test_*.py
    suite = []
    base_suite = Path("flows") / "test-plans"
    if base_suite.exists():
        for plan_dir in sorted(base_suite.iterdir()):
            if not plan_dir.is_dir():
                continue
            sc_dir   = plan_dir / "scenarios"
            clean_dir = plan_dir / "cleaned"
            if not sc_dir.exists():
                continue
            pending = 0
            for sc in sc_dir.iterdir():
                if not sc.is_dir():
                    continue
                raw = sc / f"{sc.name}.py"
                if not raw.exists():
                    continue
                py_name   = sc.name.replace("-", "_")
                test_file = clean_dir / f"test_{py_name}.py"
                if not test_file.exists():
                    pending += 1
            if pending > 0:
                suite.append({"name": plan_dir.name, "pending": pending})

    return {"single": single, "suite": suite}


def _home_ctx(error: str = "", open_plan: str = "") -> dict:
    """Contexto completo para renderizar home.html sem Jinja2 UndefinedError."""
    return dict(
        plans=_all_suite_plans(),
        suite_plans=_all_suite_plans(),
        scenarios=_available_scenarios(),
        open_plan=open_plan,
        plan_scenarios=_plan_scenarios(open_plan) if open_plan else [],
        error=error,
    )


def _cors(response):
    """Adiciona headers CORS para permitir chamadas cross-origin (localhost)."""
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ── services (singleton por processo) ────────────────────────────────────────

_claude = ClaudeClient()           # usa ANTHROPIC_API_KEY do ambiente
_transformer_svc = ScenarioTransformerService(StepTransformer(_claude))

# ── subprocesso de gravação (single-user local) ───────────────────────────────

_proc: subprocess.Popen | None = None


def _kill_proc():
    """Termina o processo de gravação em curso, se houver."""
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


# ── jobs de processamento assíncrono ─────────────────────────────────────────
# job_id -> {"status": "running"|"done", "created_at": float, ...}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()          # protege check de conclusão de batch
_JOB_TTL = 3600  # 1 hora — jobs órfãos são removidos


def _evict_old_jobs():
    """Remove jobs concluídos há mais de _JOB_TTL segundos."""
    now = _time.monotonic()
    stale = [jid for jid, j in _jobs.items()
             if j["status"] == "done" and now - j.get("created_at", now) > _JOB_TTL]
    for jid in stale:
        del _jobs[jid]


def _safe_name(name: str) -> str:
    """Garante que um nome de plano/cenário contenha só chars seguros para path."""
    return _re.sub(r"[^a-zA-Z0-9_\-]", "", name)


# ── helpers ───────────────────────────────────────────────────────────────────

def _available_plans() -> list[dict]:
    """Retorna planos que têm pasta cleaned/ com pelo menos um test_*.py (para execução)."""
    base = Path("flows") / "test-plans"
    if not base.exists():
        return []
    plans = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        cleaned = d / "cleaned"
        tests = list(cleaned.glob("test_*.py")) if cleaned.exists() else []
        if tests:
            plans.append({
                "name": d.name,
                "count": len(tests),
                "path": str(cleaned),
            })
    return plans


def _all_suite_plans() -> list[dict]:
    """Retorna TODOS os planos existentes, incluindo os sem testes processados ainda."""
    base = Path("flows") / "test-plans"
    if not base.exists():
        return []
    plans = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        # Conta cenários gravados (raw)
        scenarios_dir = d / "scenarios"
        raw_count = sum(
            1 for s in scenarios_dir.iterdir()
            if s.is_dir() and (s / f"{s.name}.py").exists()
        ) if scenarios_dir.exists() else 0
        # Conta testes processados (cleaned)
        cleaned = d / "cleaned"
        clean_count = len(list(cleaned.glob("test_*.py"))) if cleaned.exists() else 0
        has_bdd = (d / f"{d.name}.feature").exists()
        if raw_count > 0 or clean_count > 0:
            plans.append({
                "name":        d.name,
                "raw_count":   raw_count,
                "clean_count": clean_count,
                "has_bdd":     has_bdd,
            })
    return plans


def _evidence_library() -> list[dict]:
    """Retorna todas as unidades de teste com seus screenshots de evidência."""
    library: list[dict] = []

    # ── Unity tests ────────────────────────────────────────────────────────
    unity_base = Path("flows") / "unity-test"
    if unity_base.exists():
        for d in sorted(unity_base.iterdir()):
            if not d.is_dir():
                continue
            ev_dir = d / "evidences"
            images = sorted(ev_dir.glob("*.png")) if ev_dir.exists() else []
            feature_file = d / f"{d.name}.feature"
            feature_content = ""
            if feature_file.exists():
                try:
                    feature_content = feature_file.read_text(encoding="utf-8")
                except Exception:
                    pass
            if images:
                library.append({
                    "type":            "unity",
                    "name":            d.name,
                    "plan":            None,
                    "count":           len(images),
                    "images":          [{"name": f.name, "path": str(f.resolve())} for f in images],
                    "feature_content": feature_content,
                })

    # ── Test plans (SUITE) ─────────────────────────────────────────────────
    plans_base = Path("flows") / "test-plans"
    if plans_base.exists():
        for plan_dir in sorted(plans_base.iterdir()):
            if not plan_dir.is_dir():
                continue
            images: list[Path] = []

            # LLM coloca em cleaned/evidences/ (Path(__file__).parent / "evidences")
            cleaned_ev = plan_dir / "cleaned" / "evidences"
            if cleaned_ev.exists():
                images.extend(sorted(cleaned_ev.glob("*.png")))

            # Domínio coloca em evidences/<scenario_name>/
            domain_ev = plan_dir / "evidences"
            if domain_ev.exists():
                for sc_dir in sorted(domain_ev.iterdir()):
                    if sc_dir.is_dir():
                        images.extend(sorted(sc_dir.glob("*.png")))

            plan_feature = plan_dir / f"{plan_dir.name}.feature"
            plan_feature_content = ""
            if plan_feature.exists():
                try:
                    plan_feature_content = plan_feature.read_text(encoding="utf-8")
                except Exception:
                    pass
            if images:
                library.append({
                    "type":            "suite",
                    "name":            plan_dir.name,
                    "plan":            plan_dir.name,
                    "count":           len(images),
                    "images":          [{"name": f.name, "path": str(f.resolve())} for f in images],
                    "feature_content": plan_feature_content,
                })

    return library


def _plan_scenarios(plan_name: str) -> list[dict]:
    """Retorna cenários já gravados/processados de um test-plan SUITE."""
    scenarios_dir = Path("flows") / "test-plans" / plan_name / "scenarios"
    cleaned_dir   = Path("flows") / "test-plans" / plan_name / "cleaned"
    if not scenarios_dir.exists():
        return []
    result = []
    for d in sorted(scenarios_dir.iterdir()):
        if not d.is_dir():
            continue
        raw = d / f"{d.name}.py"
        if not raw.exists():
            continue
        py_name   = d.name.replace("-", "_")
        test_file = cleaned_dir / f"test_{py_name}.py"
        result.append({
            "name":      d.name,
            "processed": test_file.exists(),
        })
    return result


def _failed_test_files() -> set[str]:
    """Lê o cache do pytest e retorna paths posix de arquivos com falhas."""
    cache = Path(".pytest_cache") / "v" / "cache" / "lastfailed"
    if not cache.exists():
        return set()
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        # chave: "flows/.../test_foo.py::test_name[param]" ou só "flows/.../test_foo.py"
        return {k.split("::")[0] for k in data.keys()}
    except Exception:
        return set()


def _available_scenarios() -> list[dict]:
    """Retorna cenários unity-test com status: failed | ok | raw."""
    failed = _failed_test_files()
    base = Path("flows") / "unity-test"
    if not base.exists():
        return []
    scenarios = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        raw_file = d / f"{d.name}.py"
        if not raw_file.exists():
            continue  # pasta sem gravação
        py_name = d.name.replace("-", "_")
        test_file = d / f"test_{py_name}.py"
        has_test = test_file.exists()
        is_failed = has_test and (test_file.as_posix() in failed)
        status = "failed" if is_failed else ("ok" if has_test else "raw")
        has_bdd = (d / f"{d.name}.feature").exists()
        scenarios.append({
            "name":     d.name,
            "path":     str(test_file) if has_test else str(raw_file),
            "has_test": has_test,
            "has_bdd":  has_bdd,
            "status":   status,   # "failed" | "ok" | "raw"
        })
    return scenarios



def _normalize_url(url: str) -> str:
    url = url.strip()
    if url and "://" not in url:
        url = f"http://{url}"
    return url


def _write_flag(scenario: Scenario, flag_name: str) -> None:
    """Escreve um arquivo de flag de status na pasta do cenário.

    Formato KEY=VALUE compatível com cleaner.bat.
    Flags usados no pipeline:
      ready-bdd          → transform concluído, aguardando geração de BDD
      ready-for-testing  → BDD gerado, cenário pronto para execução
      transform-failed   → erro na limpeza do código
    """
    try:
        flag_path = scenario.scenario_dir / f"{flag_name}.flag"
        lines = [
            f"SCENARIO={scenario.name}",
            f"MODE={scenario.mode.value}",
            f"CLEAN={scenario.clean_path.resolve()}",
            f"FEATURE={scenario.feature_path.resolve()}",
        ]
        if scenario.plan_name:
            lines.append(f"PLAN={scenario.plan_name}")
        flag_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass  # flags são informativos — nunca falhar por causa deles


def _remove_flag(scenario: Scenario, flag_name: str) -> None:
    """Remove um arquivo de flag de status da pasta do cenário."""
    try:
        flag_path = scenario.scenario_dir / f"{flag_name}.flag"
        flag_path.unlink(missing_ok=True)
    except Exception:
        pass


def _to_scenario(s: dict) -> Scenario:
    mode = ExecutionMode[s["mode"]]
    plan_name = s.get("plan_name") or None
    if mode == ExecutionMode.SUITE and not plan_name:
        raise ValueError("plan_name é obrigatório para cenários SUITE")
    return Scenario(
        name=s["name"],
        url=s.get("url", ""),
        mode=mode,
        plan_name=plan_name,
    )


def _safe_transform(scenario: Scenario) -> tuple[bool, str]:
    """Limpeza via Claude CLI headless (claude -p), chamado diretamente.

    Filtra o código gravado, escreve um arquivo de prompt temporário e chama
    'claude -p' como subprocess.  Claude usa as ferramentas Read/Write para
    criar o arquivo limpo diretamente.
    """
    from orchestrator_flows.ia_prompting.prompts.transform_playwright import (
        TransformPlaywright,
    )

    try:
        if not scenario.raw_path.exists():
            return False, f"Arquivo não encontrado: {scenario.raw_path}"

        with scenario.raw_path.open("r", encoding="utf-8") as f:
            code = f.read()

        filtered = _transformer_svc.extract_relevant_code(code)
        if not filtered:
            return False, "Nenhuma linha relevante encontrada no script gravado."

        scenario.clean_path.parent.mkdir(parents=True, exist_ok=True)

        clean_path_abs = str(scenario.clean_path.resolve())

        # Escreve o prompt completo em arquivo temporário (evita limite de arg)
        prompt_file = scenario.scenario_dir / "_transform_prompt.txt"
        prompt_file.write_text(
            TransformPlaywright.build_prompt(filtered)
            + f"\n\nSalve o código Python gerado em: {clean_path_abs}\n"
            + "Crie os diretórios pai com mkdir se necessário.\n",
            encoding="utf-8",
        )

        # Chama o Claude CLI passando o arquivo de prompt como instrução
        meta_prompt = (
            f"Read the file {prompt_file.resolve()} and follow every instruction in it exactly."
        )

        try:
            result = subprocess.run(
                ["claude", "-p", meta_prompt, "--allowedTools", "Read,Write,Edit"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(Path(__file__).parent),
            )
        finally:
            # Garante limpeza mesmo em caso de timeout ou erro
            prompt_file.unlink(missing_ok=True)

        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "claude CLI retornou erro.")

        if not scenario.clean_path.exists():
            return False, "Claude CLI não criou o arquivo limpo."

        return True, str(scenario.clean_path)

    except subprocess.TimeoutExpired:
        return False, "Timeout (5 min): Claude CLI demorou muito para processar."
    except FileNotFoundError:
        return False, "Claude CLI não encontrado. Verifique se o Claude Code está instalado."
    except Exception as exc:
        return False, str(exc)


def _safe_bdd(scenario: Scenario) -> tuple[bool, str]:
    """Gera BDD de um cenário SINGLE via Claude CLI headless.

    Lê clean_path (ou raw_path como fallback) e pede ao Claude para imprimir
    o Gherkin no stdout (modo -p sem Write tool). O Python captura o output e
    salva o arquivo .feature — mais confiável do que depender do Claude usar
    a Write tool corretamente.
    """
    try:
        source = scenario.clean_path if scenario.clean_path.exists() else scenario.raw_path
        if not source.exists():
            return False, f"Arquivo não encontrado: {source}"

        code = source.read_text(encoding="utf-8")

        prompt = (
            f"The following is a Python Playwright test for the scenario '{scenario.name}'.\n\n"
            f"```python\n{code}\n```\n\n"
            f"Convert it to a Gherkin BDD Feature file.\n"
            f"Rules:\n"
            f"- Start with: Feature: {scenario.name.replace('-', ' ').title()}\n"
            f"- Include one or more Scenario: blocks\n"
            f"- Use Given/When/Then format\n"
            f"- Output ONLY the Gherkin text — no code fences, no explanations, no markdown\n"
        )

        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
            cwd=str(Path(__file__).parent),
        )

        if result.returncode != 0:
            return False, result.stderr or result.stdout or "claude CLI retornou erro."

        gherkin = result.stdout.strip()
        if not gherkin or "Feature:" not in gherkin:
            return False, "Claude não gerou conteúdo Gherkin válido."

        # Python salva o arquivo — não depende do Claude usar Write tool
        scenario.feature_path.parent.mkdir(parents=True, exist_ok=True)
        scenario.feature_path.write_text(gherkin, encoding="utf-8")

        return True, str(scenario.feature_path)

    except subprocess.TimeoutExpired:
        return False, "Timeout: Claude CLI demorou muito para gerar BDD."
    except FileNotFoundError:
        return False, "Claude CLI não encontrado."
    except Exception as exc:
        return False, str(exc)


def _safe_bdd_suite(plan_name: str) -> tuple[bool, str]:
    """Gera BDD consolidado de um plano SUITE via Claude CLI headless.

    Lê TODOS os cenários (clean ou raw), embute o código direto no prompt,
    Claude imprime o Gherkin no stdout e o Python salva o arquivo .feature.
    """
    try:
        plan_dir = Path("flows") / "test-plans" / plan_name
        scenarios_dir = plan_dir / "scenarios"
        cleaned_dir   = plan_dir / "cleaned"

        if not scenarios_dir.exists():
            return False, f"Plano não encontrado: {plan_name}"

        # Coleta todos os cenários (clean_path preferido, raw como fallback)
        parts: list[str] = []
        for sc_dir in sorted(scenarios_dir.iterdir()):
            if not sc_dir.is_dir():
                continue
            py_name = sc_dir.name.replace("-", "_")
            clean = cleaned_dir / f"test_{py_name}.py"
            raw   = sc_dir / f"{sc_dir.name}.py"
            source = clean if clean.exists() else (raw if raw.exists() else None)
            if source is None:
                continue
            code = source.read_text(encoding="utf-8").strip()
            if code:
                parts.append(f"SCENARIO: {sc_dir.name}\n\n```python\n{code}\n```")

        if not parts:
            return False, "Nenhum cenário com código encontrado."

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

        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=240,
            cwd=str(Path(__file__).parent),
        )

        if result.returncode != 0:
            return False, result.stderr or result.stdout or "claude CLI retornou erro."

        gherkin = result.stdout.strip()
        if not gherkin or "Feature:" not in gherkin:
            return False, "Claude não gerou conteúdo Gherkin válido."

        # Python salva o arquivo — não depende do Claude usar Write tool
        feature_path = plan_dir / f"{plan_name}.feature"
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        feature_path.write_text(gherkin, encoding="utf-8")

        return True, str(feature_path)

    except subprocess.TimeoutExpired:
        return False, "Timeout: Claude CLI demorou muito para gerar BDD da bateria."
    except FileNotFoundError:
        return False, "Claude CLI não encontrado."
    except Exception as exc:
        return False, str(exc)


def _pytest_worker(job_id: str, cmd: list, plan: str, evidences_url: str, back_url: str):
    """Worker de thread: roda pytest e guarda resultado em _jobs."""
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
    _jobs[job_id].update({
        "status":        "done",
        "output":        output,
        "passed":        result.returncode == 0,
        "plan":          plan,
        "evidences_url": evidences_url,
        "back_url":      back_url,
    })


def _batch_scenario_worker(job_id: str, idx: int, sc: "Scenario"):
    """Worker module-level: processa UM cenário de batch em paralelo."""
    _jobs[job_id]["scenarios"][idx]["status"] = "running"
    try:
        ok, detail = _safe_transform(sc)
    except Exception as exc:
        ok, detail = False, str(exc)
    _jobs[job_id]["scenarios"][idx].update({"status": "done", "ok": ok, "detail": detail})
    # Escreve flag para o bdd_generator.py processar em seguida
    _write_flag(sc, "ready-bdd") if ok else _write_flag(sc, "transform-failed")
    # Lock evita race condition: dois threads passando pelo check ao mesmo tempo
    with _jobs_lock:
        if all(s["status"] == "done" for s in _jobs[job_id]["scenarios"]):
            _jobs[job_id]["status"] = "done"


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    # Só limpa a sessão se não houver fluxo ativo em andamento
    if "scenario" not in session:
        session.clear()
    open_plan = _safe_name(request.args.get("plan", ""))
    all_plans = _all_suite_plans()   # computado uma vez para ambas as chaves
    return render_template(
        "home.html",
        plans=all_plans,
        suite_plans=all_plans,
        scenarios=_available_scenarios(),
        open_plan=open_plan,
        plan_scenarios=_plan_scenarios(open_plan) if open_plan else [],
        error="",
    )


@app.route("/configure", methods=["POST"])
def configure():
    global _proc
    mode = request.form["mode"]

    if mode == "single":
        name = request.form.get("name", "").strip()
        url  = _normalize_url(request.form.get("url", ""))
        if not name or not url:
            return render_template("home.html", **_home_ctx("Preencha todos os campos."))

        session["scenario"] = {"name": name, "url": url, "mode": "SINGLE"}
        scenario = _to_scenario(session["scenario"])
        scenario.ensure_dirs()
        _kill_proc()
        _proc = subprocess.Popen(
            [
                sys.executable, "-m", "playwright", "codegen",
                "--target", "python",
                "-o", str(scenario.raw_path),
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return redirect(url_for("recording"))

    if mode == "reprocess":
        name = request.form.get("name", "").strip()
        if not name:
            return render_template("home.html", **_home_ctx("Informe o nome do cenário."))
        scenario = Scenario(name=name, url="", mode=ExecutionMode.SINGLE)
        if not scenario.raw_path.exists():
            return render_template("home.html", **_home_ctx(f"Cenário não encontrado: {scenario.raw_path}"))
        session["scenario"] = {"name": name, "url": "", "mode": "SINGLE"}
        return redirect(url_for("processing"))

    if mode == "suite":
        plan = request.form.get("plan", "").strip()
        name = request.form.get("name", "").strip()
        url  = _normalize_url(request.form.get("url", ""))
        if not plan or not name or not url:
            return render_template("home.html", **_home_ctx("Preencha todos os campos da bateria.", open_plan=plan))
        session["scenario"] = {"name": name, "url": url, "mode": "SUITE", "plan_name": plan}
        scenario = _to_scenario(session["scenario"])
        scenario.ensure_dirs()
        _kill_proc()
        _proc = subprocess.Popen(
            [
                sys.executable, "-m", "playwright", "codegen",
                "--target", "python",
                "-o", str(scenario.raw_path),
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return redirect(url_for("recording"))

    if mode == "regression":
        plan = request.form.get("plan", "").strip()
        if not plan:
            return render_template("home.html", **_home_ctx("Informe o nome da bateria."))
        return redirect(url_for("regression", plan_name=plan))

    return render_template("home.html", **_home_ctx(f"Modo inválido: {mode}."))


@app.route("/process-plan/<plan_name>")
def process_plan(plan_name: str):
    """Processa em batch todos os cenários não processados de um plano SUITE."""
    plan_name = _safe_name(plan_name)
    scenarios_dir = Path("flows") / "test-plans" / plan_name / "scenarios"
    cleaned_dir   = Path("flows") / "test-plans" / plan_name / "cleaned"

    if not scenarios_dir.exists():
        return render_template("home.html", **_home_ctx(f"Plano não encontrado: {plan_name}"))

    # Coleta cenários sem test_*.py gerado
    unprocessed = []
    for d in sorted(scenarios_dir.iterdir()):
        if not d.is_dir():
            continue
        raw = d / f"{d.name}.py"
        if not raw.exists():
            continue
        py_name   = d.name.replace("-", "_")
        test_file = cleaned_dir / f"test_{py_name}.py"
        if not test_file.exists():
            unprocessed.append(Scenario(name=d.name, url="", mode=ExecutionMode.SUITE,
                                        plan_name=plan_name))

    if not unprocessed:
        return render_template("home.html", **_home_ctx("Todos os cenários desta bateria já foram processados."))

    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "type": "batch",
        "plan": plan_name,
        "scenarios": [
            {"name": sc.name, "status": "pending", "ok": None, "detail": ""}
            for sc in unprocessed
        ],
        "created_at": _time.monotonic(),
    }

    # Lança uma thread por cenário — processamento paralelo
    for idx, sc in enumerate(unprocessed):
        threading.Thread(
            target=_batch_scenario_worker,
            args=(job_id, idx, sc),
            daemon=True,
        ).start()

    return redirect(url_for("batch_wait") + f"?job={job_id}&plan={plan_name}")


@app.route("/recording")
def recording():
    if "scenario" not in session:
        return redirect(url_for("home"))
    still_running = _proc is not None and _proc.poll() is None
    return render_template(
        "recording.html",
        scenario=session["scenario"],
        still_running=still_running,
    )


@app.route("/stop-recording", methods=["POST"])
def stop_recording():
    """Para o codegen. SUITE → tela de 'gravar mais ou processar'. SINGLE → processamento."""
    _kill_proc()
    scenario_dict = session.get("scenario", {})
    if scenario_dict.get("mode") == "SUITE":
        plan_name = scenario_dict.get("plan_name", "")
        return redirect(url_for("suite_recorded") + f"?plan={plan_name}")
    return redirect(url_for("processing"))


@app.route("/suite-recorded")
def suite_recorded():
    """Após gravar um cenário SUITE: mostra lista e oferece gravar mais ou processar tudo."""
    plan_name = _safe_name(request.args.get("plan", ""))
    scenario  = session.get("scenario", {})
    recorded  = _plan_scenarios(plan_name) if plan_name else []
    return render_template(
        "suite_recorded.html",
        plan=plan_name,
        recorded=recorded,
        last_scenario=scenario,
    )


@app.route("/processing")
def processing():
    if "scenario" not in session:
        pending = _pending_processing()
        return render_template("processing_continue.html", pending=pending)
    return render_template("processing.html", scenario=session["scenario"])


@app.route("/run-process", methods=["POST"])
def run_process():
    if "scenario" not in session:
        pending = _pending_processing()
        return render_template("processing_continue.html", pending=pending)

    do_transform = "transform" in request.form
    do_bdd       = "bdd" in request.form
    scenario_dict = session["scenario"]
    scenario      = _to_scenario(scenario_dict)

    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {"status": "running", "results": [], "steps": {"transform": do_transform, "bdd": do_bdd}, "created_at": _time.monotonic()}

    def _worker(job_id: str, scenario: Scenario, do_transform: bool, do_bdd: bool):
        results: list[tuple[bool, str, str]] = []
        try:
            if do_transform:
                ok, detail = _safe_transform(scenario)
                label = "✅ Código limpo salvo" if ok else "❌ Erro na limpeza"
                results.append((ok, label, detail))
                # Escreve flag de status após transform
                if ok:
                    _write_flag(scenario, "ready-bdd")
                else:
                    _write_flag(scenario, "transform-failed")
            if do_bdd:
                ok, detail = _safe_bdd(scenario)
                label = "✅ Feature gerada" if ok else "❌ Erro no BDD"
                results.append((ok, label, detail))
                # Atualiza flags: remove ready-bdd, escreve ready-for-testing
                _remove_flag(scenario, "ready-bdd")
                if ok:
                    _write_flag(scenario, "ready-for-testing")
            _jobs[job_id]["results"] = results
            _jobs[job_id]["status"]  = "done"
        except Exception as exc:
            _jobs[job_id]["results"] = [(False, "❌ Erro inesperado", str(exc))]
            _jobs[job_id]["status"]  = "done"

    threading.Thread(target=_worker, args=(job_id, scenario, do_transform, do_bdd), daemon=True).start()
    return redirect(url_for("processing_wait", job=job_id))


@app.route("/processing-wait")
def processing_wait():
    job_id = request.args.get("job", "")
    label  = request.args.get("label", "")
    scenario = session.get("scenario") or {"name": label or "…"}
    return render_template("processing_wait.html", scenario=scenario, job_id=job_id)


@app.route("/api/job-status/<job_id>")
def api_job_status(job_id: str):
    """Polling sem sessão: recebe job_id direto na URL."""
    if job_id not in _jobs:
        return jsonify({"status": "unknown"})
    job = _jobs[job_id]
    if job["status"] not in ("done", "ready"):
        return jsonify({"status": "running"})
    _jobs[job_id]["status"] = "ready"   # marca como consumível por /results/<job_id>
    return jsonify({"status": "done", "job_id": job_id})


@app.route("/results/<job_id>")
def results_by_job(job_id: str):
    """Exibe resultado do processamento IA lendo direto de _jobs.

    Jobs do tipo 'bdd' (generate_suite_bdd) redirecionam para /bdd-result/<plan>
    que exibe o conteúdo da feature e o botão de execução.

    Renderiza diretamente (sem redirect extra) para evitar perda de dados de
    sessão entre requests. Usa cache de sessão como fallback se o job já foi
    consumido (double-request, back-button, etc.).
    """
    job = _jobs.pop(job_id, None)

    # Fallback: job já foi consumido mas sessão ainda tem os dados
    if not job:
        cached = session.get("results")
        if cached is not None:
            return redirect(url_for("results"))
        return redirect(url_for("home"))

    job_type = job.get("type", "process")

    if job_type == "bdd":
        # Redireciona para a tela dedicada de resultado BDD
        plan = job.get("plan", "")
        ok   = job.get("ok", False)
        detail = job.get("detail", "")
        feature_content = ""
        if ok and plan:
            feature_path = Path("flows") / "test-plans" / plan / f"{plan}.feature"
            if feature_path.exists():
                feature_content = feature_path.read_text(encoding="utf-8")
        session["bdd_result"] = {
            "plan": plan, "ok": ok, "detail": detail,
            "feature_content": feature_content,
        }
        session.modified = True
        return redirect(url_for("bdd_result_page", plan_name=plan))

    # Monta contexto e salva em sessão (cache para back-button)
    res        = job.get("results", [])
    last_steps = job.get("steps", {})
    scenario   = session.get("scenario") or job.get("scenario_dict")
    session["results"]    = res
    session["last_steps"] = last_steps
    session.modified = True

    has_failure = any(not ok for ok, *_ in res)
    suite_scenarios: list[dict] = []
    if scenario and scenario.get("mode") == "SUITE":
        suite_scenarios = _plan_scenarios(scenario.get("plan_name", ""))

    # Lê conteúdo da feature gerada para exibir inline na tela de resultado
    feature_content = ""
    for ok, _label, detail in res:
        if ok and str(detail).endswith(".feature"):
            try:
                fp = Path(detail)
                if fp.exists():
                    feature_content = fp.read_text(encoding="utf-8")
            except Exception:
                pass
            break

    # Renderiza direto — sem redirect extra que poderia perder a sessão
    return render_template(
        "results.html",
        results=res,
        scenario=scenario,
        has_failure=has_failure,
        last_steps=last_steps,
        suite_scenarios=suite_scenarios,
        feature_content=feature_content,
    )


@app.route("/results")
def results():
    res        = session.get("results", [])
    last_steps = session.get("last_steps", {})
    scenario   = session.get("scenario")
    has_failure = any(not ok for ok, *_ in res)
    # Para baterias SUITE: lista cenários já existentes naquele plano
    suite_scenarios: list[dict] = []
    if scenario and scenario.get("mode") == "SUITE":
        suite_scenarios = _plan_scenarios(scenario.get("plan_name", ""))
    # Lê conteúdo da feature gerada para exibir inline
    feature_content = ""
    for ok, _label, detail in res:
        if ok and str(detail).endswith(".feature"):
            try:
                fp = Path(detail)
                if fp.exists():
                    feature_content = fp.read_text(encoding="utf-8")
            except Exception:
                pass
            break
    return render_template(
        "results.html",
        results=res,
        scenario=scenario,
        has_failure=has_failure,
        last_steps=last_steps,
        suite_scenarios=suite_scenarios,
        feature_content=feature_content,
    )


@app.route("/regression/<plan_name>")
def regression(plan_name: str):
    plan_name = _safe_name(plan_name)
    _evict_old_jobs()
    cleaned_dir = Path("flows") / "test-plans" / plan_name / "cleaned"

    if not cleaned_dir.exists():
        return render_template(
            "regression.html",
            output=f"Pasta não encontrada: {cleaned_dir}",
            passed=False,
            plan=plan_name,
        )

    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {"status": "running", "kind": "pytest", "plan": plan_name,
                     "evidences_url": f"/regression/{plan_name}/evidences",
                     "back_url": "/", "created_at": _time.monotonic()}

    threading.Thread(
        target=_pytest_worker,
        args=(job_id,
              [sys.executable, "-m", "pytest", str(cleaned_dir), "--headed", "-v", "--tb=short"],
              plan_name,
              f"/regression/{plan_name}/evidences",
              "/"),
        daemon=True,
    ).start()
    return redirect(url_for("pytest_wait", label=plan_name, job=job_id))


@app.route("/pytest-wait/<label>")
def pytest_wait(label: str):
    """Tela de espera enquanto o pytest roda em background."""
    job_id = request.args.get("job", "")
    return render_template("pytest_wait.html", label=label, job_id=job_id)


@app.route("/api/pytest-status/<job_id>")
def api_pytest_status(job_id: str):
    """Polling sem sessão: recebe job_id direto na URL."""
    if job_id not in _jobs:
        return jsonify({"status": "unknown"})
    job = _jobs[job_id]
    if job["status"] not in ("done", "ready"):
        return jsonify({"status": "running"})
    _jobs[job_id]["status"] = "ready"
    return jsonify({"status": "done", "job_id": job_id})


# ── Batch wait (processamento paralelo de bateria) ─────────────────────────────

@app.route("/batch-wait")
def batch_wait():
    """Tela de acompanhamento em tempo real do processamento paralelo de batch."""
    job_id = request.args.get("job", "")
    plan   = request.args.get("plan", "")
    return render_template("batch_wait.html", job_id=job_id, plan=plan)


@app.route("/api/batch-status/<job_id>")
def api_batch_status(job_id: str):
    """Retorna status detalhado de cada cenário do batch para polling da UI."""
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"status": "unknown"})
    return jsonify({
        "status":    job["status"],
        "scenarios": job.get("scenarios", []),
        "plan":      job.get("plan", ""),
    })


@app.route("/batch-result/<job_id>")
def batch_result(job_id: str):
    """Tela de resultado após processamento em batch."""
    job = _jobs.pop(job_id, None)
    if not job:
        return redirect(url_for("home"))
    scenarios = job.get("scenarios", [])
    plan      = job.get("plan", "")
    passed    = [s for s in scenarios if s.get("ok")]
    failed    = [s for s in scenarios if not s.get("ok")]
    # Exibe BDD existente se já gerado em rodada anterior
    feature_content = ""
    if plan:
        fp = Path("flows") / "test-plans" / plan / f"{plan}.feature"
        if fp.exists():
            try:
                feature_content = fp.read_text(encoding="utf-8")
            except Exception:
                pass
    return render_template(
        "batch_result.html",
        plan=plan,
        scenarios=scenarios,
        passed=passed,
        failed=failed,
        job_id=job_id,
        feature_content=feature_content,
    )


@app.route("/pytest-result/<job_id>")
def pytest_result(job_id: str):
    """Exibe o resultado do pytest lendo direto de _jobs pelo job_id."""
    job = _jobs.pop(job_id, None)
    if not job:
        return redirect(url_for("home"))
    # Guarda na sessão para o /report conseguir gerar o relatório
    session["pytest_result"] = {
        "output":        job["output"],
        "passed":        job["passed"],
        "plan":          job["plan"],
        "evidences_url": job.get("evidences_url"),
        "back_url":      job.get("back_url", "/"),
    }
    session.modified = True
    return render_template(
        "regression.html",
        output=job["output"],
        passed=job["passed"],
        plan=job["plan"],
        evidences_url=job.get("evidences_url"),
        back_url=job.get("back_url", "/"),
    )


@app.route("/regression/<plan_name>/evidences")
def regression_evidences(plan_name: str):
    """Galeria de evidências de uma bateria (SUITE)."""
    plan_name = _safe_name(plan_name)
    evidences_dir = Path("flows") / "test-plans" / plan_name / "cleaned" / "evidences"
    evidences = (
        [{"name": f.name, "path": str(f.resolve())}
         for f in sorted(evidences_dir.glob("*.png"))]
        if evidences_dir.exists()
        else []
    )
    return render_template(
        "evidences.html",
        plan=plan_name,
        back_url=f"/regression/{plan_name}",
        evidences=evidences,
    )


@app.route("/run-test/<scenario_name>")
def run_test(scenario_name: str):
    """Executa um cenário unity-test isolado."""
    scenario_name = _safe_name(scenario_name)
    _evict_old_jobs()
    scenario = Scenario(name=scenario_name, url="", mode=ExecutionMode.SINGLE)
    if not scenario.clean_path.exists():
        return render_template("home.html", **_home_ctx(f"Teste não encontrado: {scenario.clean_path}"))

    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {"status": "running", "kind": "pytest", "plan": scenario_name,
                     "evidences_url": f"/run-test/{scenario_name}/evidences",
                     "back_url": "/", "created_at": _time.monotonic()}

    threading.Thread(
        target=_pytest_worker,
        args=(job_id,
              [sys.executable, "-m", "pytest", str(scenario.clean_path), "--headed", "-v", "--tb=short"],
              scenario_name,
              f"/run-test/{scenario_name}/evidences",
              "/"),
        daemon=True,
    ).start()
    return redirect(url_for("pytest_wait", label=scenario_name, job=job_id))


@app.route("/run-test/<scenario_name>/evidences")
def run_test_evidences(scenario_name: str):
    """Galeria de evidências de um cenário isolado (SINGLE)."""
    scenario_name = _safe_name(scenario_name)
    scenario = Scenario(name=scenario_name, url="", mode=ExecutionMode.SINGLE)
    evidences_dir = scenario.evidences_dir
    evidences = (
        [{"name": f.name, "path": str(f.resolve())}
         for f in sorted(evidences_dir.glob("*.png"))]
        if evidences_dir.exists()
        else []
    )
    return render_template(
        "evidences.html",
        plan=scenario_name,
        back_url=f"/run-test/{scenario_name}",
        evidences=evidences,
    )


_FLOWS_ROOT = Path("flows").resolve()


def _safe_image_path(img_path: str):
    """Resolve e valida que o path está dentro de flows/. Retorna Path ou None."""
    if not img_path:
        return None
    try:
        p = Path(img_path).resolve()
        # Deve estar dentro da pasta flows/ do projeto
        p.relative_to(_FLOWS_ROOT)
        if p.exists() and p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            return p
    except (ValueError, Exception):
        pass
    return None


@app.route("/evidence-image")
def evidence_image():
    """Serve uma imagem de evidência — restrito à pasta flows/."""
    p = _safe_image_path(request.args.get("path", "").strip())
    if not p:
        return "Não encontrado ou acesso negado", 404
    return send_file(str(p), mimetype="image/png")


@app.route("/library")
def library():
    return render_template("library.html", library=_evidence_library())


def _extract_elements(test_path: Path) -> list[dict]:
    """Extrai ações e seletores Playwright de um arquivo de teste Python.

    Retorna lista de dicts com icon, kind (goto/click/fill/screenshot/human) e label.
    Útil para mostrar na biblioteca quais elementos da UI cada cenário toca.
    """
    if not test_path.exists():
        return []
    try:
        text = test_path.read_text(encoding="utf-8")
    except Exception:
        return []

    elements = []
    for line in text.splitlines():
        s = line.strip()
        if (not s or s.startswith('#') or s.startswith('from ')
                or s.startswith('import ') or s.startswith('_EVIDENCES')
                or s.startswith('def ') or s.startswith('class ')):
            continue

        # page.goto("url")
        m = _re.search(r'page\.goto\("([^"]+)"\)', s)
        if m:
            url = m.group(1)
            # Extrai só o path da URL para exibição compacta
            try:
                from urllib.parse import urlparse as _up
                pth = _up(url).path or url
            except Exception:
                pth = url
            elements.append({'kind': 'goto', 'icon': '🔗', 'label': pth})
            continue

        # page.get_by_role("role", name="name")
        m = _re.search(r'page\.get_by_role\("([^"]+)"(?:,\s*name="([^"]*)")?\)', s)
        if m:
            role, name = m.group(1), m.group(2) or ''
            action = 'fill' if '.fill(' in s else 'click'
            icons = {'button': '🔘', 'textbox': '📝', 'heading': '🏷️', 'link': '🔗'}
            elements.append({'kind': action, 'icon': icons.get(role, '📌'),
                             'label': f'{role} "{name}"' if name else role})
            continue

        # page.get_by_text("text")
        m = _re.search(r'page\.get_by_text\("([^"]+)"\)', s)
        if m:
            txt = m.group(1)
            elements.append({'kind': 'click', 'icon': '💬', 'label': f'"{txt}"'})
            continue

        # page.get_by_label("label")
        m = _re.search(r'page\.get_by_label\("([^"]+)"\)', s)
        if m:
            elements.append({'kind': 'click', 'icon': '🏷️', 'label': m.group(1)})
            continue

        # page.locator("selector")
        m = _re.search(r'page\.locator\("([^"]+)"\)', s)
        if m:
            elements.append({'kind': 'click', 'icon': '🔍', 'label': m.group(1)})
            continue

        # page.screenshot(...)
        if 'page.screenshot(' in s:
            m = _re.search(r'"([^"]+\.png)"', s)
            fname = m.group(1).rsplit('/', 1)[-1] if m else 'screenshot.png'
            elements.append({'kind': 'screenshot', 'icon': '📸', 'label': fname})
            continue

        # HumanIntervention.required(...)
        if 'HumanIntervention.required(' in s:
            elements.append({'kind': 'human', 'icon': '🧑', 'label': 'Intervenção humana necessária'})
            continue

    return elements


def _extract_rule(feature_path: Path) -> dict:
    """Extrai Feature e Scenarios de um arquivo .feature como regra de negócio."""
    if not feature_path.exists():
        return {"feature": "", "scenarios": []}
    try:
        text = feature_path.read_text(encoding="utf-8")
    except Exception:
        return {"feature": "", "scenarios": []}
    feature_name = ""
    scenarios = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Feature:"):
            feature_name = stripped[len("Feature:"):].strip()
        elif stripped.startswith("Scenario:") or stripped.startswith("Scenario Outline:"):
            label = "Scenario Outline:" if stripped.startswith("Scenario Outline:") else "Scenario:"
            scenarios.append(stripped[len(label):].strip())
    return {"feature": feature_name, "scenarios": scenarios}


def _build_overview() -> dict:
    """Agrega todos os cenários e planos com status completo para a página de visão geral."""
    failed_files = _failed_test_files()

    # ── SINGLE (unity-test) ────────────────────────────────────────────────
    single: list[dict] = []
    unity_base = Path("flows") / "unity-test"
    if unity_base.exists():
        for d in sorted(unity_base.iterdir()):
            if not d.is_dir():
                continue
            raw = d / f"{d.name}.py"
            if not raw.exists():
                continue
            py_name   = d.name.replace("-", "_")
            test_file = d / f"test_{py_name}.py"
            feat_file = d / f"{d.name}.feature"
            ev_dir    = d / "evidences"
            ev_images = sorted(ev_dir.glob("*.png")) if ev_dir.exists() else []
            has_clean = test_file.exists()
            is_failed = has_clean and (test_file.as_posix() in failed_files)
            status    = "failed" if is_failed else ("ok" if has_clean else "raw")
            feat_txt  = ""
            if feat_file.exists():
                try:
                    feat_txt = feat_file.read_text(encoding="utf-8")
                except Exception:
                    pass
            single.append({
                "name":            d.name,
                "has_raw":         True,
                "has_clean":       has_clean,
                "has_bdd":         feat_file.exists(),
                "status":          status,
                "evidence_count":  len(ev_images),
                "feature_content": feat_txt,
                "rule":            _extract_rule(feat_file),
                "elements":        _extract_elements(test_file if has_clean else raw),
                "run_url":         f"/run-test/{d.name}" if has_clean else None,
            })

    # ── SUITE (test-plans) ─────────────────────────────────────────────────
    suite: list[dict] = []
    plans_base = Path("flows") / "test-plans"
    if plans_base.exists():
        for plan_dir in sorted(plans_base.iterdir()):
            if not plan_dir.is_dir():
                continue
            sc_dir    = plan_dir / "scenarios"
            clean_dir = plan_dir / "cleaned"
            feat_file = plan_dir / f"{plan_dir.name}.feature"
            if not sc_dir.exists():
                continue
            scenarios: list[dict] = []
            for s in sorted(sc_dir.iterdir()):
                if not s.is_dir():
                    continue
                raw = s / f"{s.name}.py"
                if not raw.exists():
                    continue
                py_name   = s.name.replace("-", "_")
                clean_f   = clean_dir / f"test_{py_name}.py"
                scenarios.append({
                    "name":      s.name,
                    "has_clean": clean_f.exists(),
                    "elements":  _extract_elements(clean_f if clean_f.exists() else raw),
                })
            if not scenarios:
                continue
            feat_txt = ""
            if feat_file.exists():
                try:
                    feat_txt = feat_file.read_text(encoding="utf-8")
                except Exception:
                    pass
            clean_count = sum(1 for s in scenarios if s["has_clean"])
            suite.append({
                "name":            plan_dir.name,
                "scenarios":       scenarios,
                "total":           len(scenarios),
                "clean_count":     clean_count,
                "has_bdd":         feat_file.exists(),
                "feature_content": feat_txt,
                "rule":            _extract_rule(feat_file),
                "can_run":         clean_count > 0,
            })

    return {"single": single, "suite": suite}


@app.route("/mapa")
def mapa():
    """Visão geral de todos os cenários e baterias com status completo."""
    data = _build_overview()
    # Lê REGRAS.md para exibir o glossário na biblioteca
    regras_md = ""
    regras_path = Path(__file__).parent / "REGRAS.md"
    if regras_path.exists():
        try:
            regras_md = regras_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return render_template("overview.html", single=data["single"], suite=data["suite"], regras_md=regras_md)


@app.route("/api/overview")
def api_overview():
    """JSON com todos os cenários e planos — consumido pelo polling da página /mapa."""
    return _cors(jsonify(_build_overview()))


# ── API pública (cross-project) ───────────────────────────────────────────────

BASE_URL = "http://localhost:5000"


def _image_url(abs_path: str) -> str:
    from urllib.parse import quote
    return f"{BASE_URL}/evidence-image?path={quote(abs_path)}"


@app.route("/api/library")
def api_library():
    """
    Retorna todas as unidades de teste com seus screenshots.

    GET /api/library
    [
      {
        "type": "unity" | "suite",
        "name": "nome-do-cenario",
        "plan": null | "nome-do-plano",
        "count": 3,
        "images": [
          { "name": "01_home.png", "url": "http://localhost:5000/evidence-image?path=..." }
        ]
      }
    ]
    """
    data = []
    for unit in _evidence_library():
        data.append({
            "type":   unit["type"],
            "name":   unit["name"],
            "plan":   unit["plan"],
            "count":  unit["count"],
            "images": [
                {"name": img["name"], "url": _image_url(img["path"])}
                for img in unit["images"]
            ],
        })
    return _cors(jsonify(data))


@app.route("/api/plans")
def api_plans():
    """
    GET /api/plans  →  lista de test-plans disponíveis.
    [{ "name": "...", "count": 2, "run_url": "http://localhost:5000/regression/..." }]
    """
    data = [
        {
            "name":    p["name"],
            "count":   p["count"],
            "run_url": f"{BASE_URL}/regression/{p['name']}",
        }
        for p in _available_plans()
    ]
    return _cors(jsonify(data))


@app.route("/api/scenarios")
def api_scenarios():
    """
    GET /api/scenarios  →  lista de cenários unity-test com status.
    [{ "name": "...", "status": "failed"|"ok"|"raw", "run_url": "..." }]
    """
    data = [
        {
            "name":    s["name"],
            "status":  s["status"],
            "run_url": f"{BASE_URL}/run-test/{s['name']}",
        }
        for s in _available_scenarios()
    ]
    return _cors(jsonify(data))


@app.route("/api/evidence-image")
def api_evidence_image():
    """Alias CORS-friendly para /evidence-image — restrito a flows/."""
    p = _safe_image_path(request.args.get("path", "").strip())
    if not p:
        return _cors(jsonify({"error": "não encontrado ou acesso negado"})), 404
    return _cors(send_file(str(p), mimetype="image/png"))


@app.route("/report")
def report():
    """Gera relatório de execução 100% bem-sucedida."""
    import re
    from datetime import datetime

    r = session.get("pytest_result")
    if not r or not r.get("passed"):
        return redirect(url_for("home"))

    output = r.get("output", "")
    plan   = r.get("plan", "—")

    # Parseia linhas com PASSED do output -v do pytest
    # ex: "flows/.../test_foo.py::test_foo PASSED   [ 50%]"
    passed_tests = []
    for line in output.splitlines():
        line = line.strip()
        if " PASSED" not in line or "::" not in line:
            continue
        try:
            # parte antes de PASSED: "flows/.../test_foo.py::test_foo"
            before_passed = line.split(" PASSED")[0].strip()
            file_part, test_part = before_passed.rsplit("::", 1)
            passed_tests.append({
                "file": file_part.replace("\\", "/").split("/")[-1],
                "test": test_part.strip(),
            })
        except Exception:
            continue

    # Evidências (se existirem)
    ev_url  = r.get("evidences_url")
    ev_dir  = None
    images  = []
    if ev_url:
        # tenta descobrir pasta a partir da url
        if "/regression/" in ev_url:
            pname = ev_url.split("/regression/")[1].split("/")[0]
            ev_dir = Path("flows") / "test-plans" / pname / "cleaned" / "evidences"
        elif "/run-test/" in ev_url:
            sname = ev_url.split("/run-test/")[1].split("/")[0]
            sc = Scenario(name=sname, url="", mode=ExecutionMode.SINGLE)
            ev_dir = sc.evidences_dir
        if ev_dir and ev_dir.exists():
            images = [
                {"name": f.name, "url": f"/evidence-image?path={_url_quote(str(f.resolve()))}"}
                for f in sorted(ev_dir.glob("*.png"))
            ]

    # Lê a feature gerada para incluir no relatório
    feature_content = ""
    if ev_url:
        if "/regression/" in ev_url:
            pname = ev_url.split("/regression/")[1].split("/")[0]
            fp = Path("flows") / "test-plans" / pname / f"{pname}.feature"
        elif "/run-test/" in ev_url:
            sname = ev_url.split("/run-test/")[1].split("/")[0]
            fp = Path("flows") / "unity-test" / sname / f"{sname}.feature"
        else:
            fp = None
        if fp and fp.exists():
            try:
                feature_content = fp.read_text(encoding="utf-8")
            except Exception:
                pass

    return render_template(
        "report.html",
        plan=plan,
        generated_at=datetime.now().strftime("%d/%m/%Y às %H:%M"),
        passed_tests=passed_tests,
        total=len(passed_tests),
        images=images,
        ev_url=ev_url,
        feature_content=feature_content,
    )


@app.route("/bdd-result/<plan_name>")
def bdd_result_page(plan_name: str):
    """Tela dedicada de resultado do BDD — mostra feature gerada e ações."""
    plan_name = _safe_name(plan_name)
    r = session.get("bdd_result", {})
    # Fallback: lê direto do filesystem se a sessão foi perdida
    if not r or r.get("plan") != plan_name:
        feature_path = Path("flows") / "test-plans" / plan_name / f"{plan_name}.feature"
        if feature_path.exists():
            r = {
                "plan": plan_name,
                "ok": True,
                "detail": str(feature_path),
                "feature_content": feature_path.read_text(encoding="utf-8"),
            }
        else:
            r = {"plan": plan_name, "ok": False, "detail": "Feature não encontrada.", "feature_content": ""}
    return render_template(
        "bdd_result.html",
        plan=r.get("plan", plan_name),
        ok=r.get("ok", False),
        detail=r.get("detail", ""),
        feature_content=r.get("feature_content", ""),
        job_id="",
    )


@app.route("/generate-suite-bdd/<plan_name>")
def generate_suite_bdd(plan_name: str):
    """Gera BDD consolidado de um plano SUITE via Claude CLI (equivale ao CLI run_suite_flow)."""
    plan_name = _safe_name(plan_name)
    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "type": "bdd",
        "plan": plan_name,
        "created_at": _time.monotonic(),
    }

    def _worker(jid: str, pname: str):
        ok, detail = _safe_bdd_suite(pname)
        _jobs[jid].update({"status": "done", "ok": ok, "detail": detail})

    threading.Thread(target=_worker, args=(job_id, plan_name), daemon=True).start()
    return redirect(url_for("processing_wait", job=job_id, label=f"BDD {plan_name}"))


@app.route("/download-raw/single/<name>")
def download_raw_single(name: str):
    """Faz download do arquivo de gravação raw de um cenário SINGLE."""
    name = _safe_name(name)
    raw = Path("flows") / "unity-test" / name / f"{name}.py"
    if not raw.exists():
        return "Arquivo não encontrado", 404
    return send_file(str(raw.resolve()), as_attachment=True, download_name=f"{name}.py")


@app.route("/download-raw/suite/<plan>/<scenario>")
def download_raw_suite(plan: str, scenario: str):
    """Faz download do arquivo de gravação raw de um cenário SUITE."""
    plan     = _safe_name(plan)
    scenario = _safe_name(scenario)
    raw = Path("flows") / "test-plans" / plan / "scenarios" / scenario / f"{scenario}.py"
    if not raw.exists():
        return "Arquivo não encontrado", 404
    return send_file(str(raw.resolve()), as_attachment=True, download_name=f"{scenario}.py")


@app.route("/api/reprocess/single/<name>", methods=["POST"])
def reprocess_single(name: str):
    """Reprocessa (re-transforma com Claude CLI) um cenário SINGLE — apaga o código limpo e gera novamente."""
    name = _safe_name(name)
    sc = Scenario(name=name, url="", mode=ExecutionMode.SINGLE)
    if not sc.raw_path.exists():
        return jsonify({"error": "Gravação não encontrada"}), 404
    sc.clean_path.unlink(missing_ok=True)
    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {"status": "running", "type": "reprocess", "created_at": _time.monotonic()}

    def _worker(jid, scenario):
        ok, detail = _safe_transform(scenario)
        _jobs[jid].update({"status": "done", "ok": ok, "detail": detail})
        _write_flag(scenario, "ready-bdd") if ok else _write_flag(scenario, "transform-failed")

    threading.Thread(target=_worker, args=(job_id, sc), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/reprocess/suite/<plan>/<scenario>", methods=["POST"])
def reprocess_suite_scenario(plan: str, scenario: str):
    """Reprocessa (re-transforma com Claude CLI) um cenário específico de um plano SUITE."""
    plan     = _safe_name(plan)
    scenario = _safe_name(scenario)
    sc = Scenario(name=scenario, url="", mode=ExecutionMode.SUITE, plan_name=plan)
    if not sc.raw_path.exists():
        return jsonify({"error": "Gravação não encontrada"}), 404
    sc.clean_path.unlink(missing_ok=True)
    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {"status": "running", "type": "reprocess", "created_at": _time.monotonic()}

    def _worker(jid, sc_obj):
        ok, detail = _safe_transform(sc_obj)
        _jobs[jid].update({"status": "done", "ok": ok, "detail": detail})
        _write_flag(sc_obj, "ready-bdd") if ok else _write_flag(sc_obj, "transform-failed")

    threading.Thread(target=_worker, args=(job_id, sc), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    # use_reloader=False: evita que o Werkzeug reinicie o servidor ao detectar
    # mudanças em flows/ (arquivos escritos pelo Claude CLI durante o processamento
    # matavam os jobs em andamento no meio da execução).
    app.run(debug=True, use_reloader=False, port=5000)
