import json
import subprocess
import sys
import threading
import uuid as _uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for

from orchestrator_flows.domain.execution import ExecutionMode
from orchestrator_flows.domain.scenario import Scenario
from orchestrator_flows.flow_design.client_ollama import OllamaClient
from orchestrator_flows.ia_prompting.code_perform_IA import StepTransformer
from orchestrator_flows.ia_prompting.prompts.humanizer_bdd import Humanizer
from orchestrator_flows.services.bdd_service import BddGeneratorService
from orchestrator_flows.services.scenario_transformer_service import (
    ScenarioTransformerService,
)

app = Flask(__name__)
app.secret_key = "orchestrator-local"


def _cors(response):
    """Adiciona headers CORS para permitir chamadas cross-origin (localhost)."""
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ── services (singleton por processo) ────────────────────────────────────────

_ollama = OllamaClient()
_transformer_svc = ScenarioTransformerService(StepTransformer(_ollama))
_bdd_svc = BddGeneratorService(Humanizer(_ollama))

# ── subprocesso de gravação (single-user local) ───────────────────────────────

_proc: subprocess.Popen | None = None

# ── jobs de processamento assíncrono ─────────────────────────────────────────
# job_id -> {"status": "running"|"done"|"error", "results": [...], "steps": {...}}
_jobs: dict[str, dict] = {}


# ── helpers ───────────────────────────────────────────────────────────────────

def _available_plans() -> list[dict]:
    """Retorna planos que têm pasta cleaned/ com pelo menos um test_*.py."""
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
            if images:
                library.append({
                    "type":   "unity",
                    "name":   d.name,
                    "plan":   None,
                    "count":  len(images),
                    "images": [{"name": f.name, "path": str(f.resolve())} for f in images],
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

            if images:
                library.append({
                    "type":   "suite",
                    "name":   plan_dir.name,
                    "plan":   plan_dir.name,
                    "count":  len(images),
                    "images": [{"name": f.name, "path": str(f.resolve())} for f in images],
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
        scenarios.append({
            "name": d.name,
            "path": str(test_file) if has_test else str(raw_file),
            "has_test": has_test,
            "status": status,   # "failed" | "ok" | "raw"
        })
    return scenarios



def _normalize_url(url: str) -> str:
    url = url.strip()
    if url and "://" not in url:
        url = f"http://{url}"
    return url


def _to_scenario(s: dict) -> Scenario:
    return Scenario(
        name=s["name"],
        url=s.get("url", ""),
        mode=ExecutionMode[s["mode"]],
        plan_name=s.get("plan_name"),
    )


def _safe_transform(scenario: Scenario) -> tuple[bool, str]:
    """Transform sem chamar input() — compatível com Flask."""
    try:
        if not scenario.raw_path.exists():
            return False, f"Arquivo não encontrado: {scenario.raw_path}"
        with scenario.raw_path.open("r", encoding="utf-8") as f:
            code = f.read()
        filtered = _transformer_svc.extract_relevant_code(code)
        if not filtered:
            return False, "Nenhuma linha relevante encontrada no script gravado."
        clean = _transformer_svc.transformer_service.transform_to_playwright(filtered)
        clean = _transformer_svc.normalize_pytest_code(clean, scenario.name)
        scenario.clean_path.parent.mkdir(parents=True, exist_ok=True)
        scenario.clean_path.write_text(clean, encoding="utf-8")
        return True, str(scenario.clean_path)
    except Exception as exc:
        return False, str(exc)


def _safe_bdd(scenario: Scenario) -> tuple[bool, str]:
    try:
        ok = _bdd_svc.generate_single(scenario)
        return (True, str(scenario.feature_path)) if ok else (False, "BDD não gerado.")
    except Exception as exc:
        return False, str(exc)


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    session.clear()
    # Permite abrir direto na aba de bateria com plano pré-selecionado
    open_plan = request.args.get("plan", "")
    return render_template(
        "home.html",
        plans=_available_plans(),
        scenarios=_available_scenarios(),
        open_plan=open_plan,
        plan_scenarios=_plan_scenarios(open_plan) if open_plan else [],
    )


@app.route("/configure", methods=["POST"])
def configure():
    global _proc
    mode = request.form["mode"]

    if mode == "single":
        name = request.form.get("name", "").strip()
        url  = _normalize_url(request.form.get("url", ""))
        if not name or not url:
            return render_template("home.html", error="Preencha todos os campos.")

        session["scenario"] = {"name": name, "url": url, "mode": "SINGLE"}
        scenario = _to_scenario(session["scenario"])
        scenario.ensure_dirs()
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
            return render_template("home.html", error="Informe o nome do cenário.")
        scenario = Scenario(name=name, url="", mode=ExecutionMode.SINGLE)
        if not scenario.raw_path.exists():
            return render_template(
                "home.html",
                error=f"Cenário não encontrado: {scenario.raw_path}",
            )
        session["scenario"] = {"name": name, "url": "", "mode": "SINGLE"}
        return redirect(url_for("processing"))

    if mode == "suite":
        plan = request.form.get("plan", "").strip()
        name = request.form.get("name", "").strip()
        url  = _normalize_url(request.form.get("url", ""))
        if not plan or not name or not url:
            return render_template(
                "home.html",
                plans=_available_plans(),
                scenarios=_available_scenarios(),
                error="Preencha todos os campos da bateria.",
            )
        session["scenario"] = {"name": name, "url": url, "mode": "SUITE", "plan_name": plan}
        scenario = _to_scenario(session["scenario"])
        scenario.ensure_dirs()
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
            return render_template(
                "home.html",
                plans=_available_plans(),
                scenarios=_available_scenarios(),
                error="Informe o nome da bateria.",
            )
        return redirect(url_for("regression", plan_name=plan))

    return redirect(url_for("home"))


@app.route("/reprocess/<scenario_name>")
def reprocess(scenario_name: str):
    """Inicia reprocessamento de um cenário pelo nome (via card clicável)."""
    scenario = Scenario(name=scenario_name, url="", mode=ExecutionMode.SINGLE)
    if not scenario.raw_path.exists():
        return render_template(
            "home.html",
            plans=_available_plans(),
            scenarios=_available_scenarios(),
            error=f"Gravação não encontrada: {scenario.raw_path}",
        )
    session["scenario"] = {"name": scenario_name, "url": "", "mode": "SINGLE"}
    return redirect(url_for("processing"))


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
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None
    return redirect(url_for("processing"))


@app.route("/processing")
def processing():
    if "scenario" not in session:
        return redirect(url_for("home"))
    return render_template("processing.html", scenario=session["scenario"])


@app.route("/run-process", methods=["POST"])
def run_process():
    if "scenario" not in session:
        return redirect(url_for("home"))

    do_transform = "transform" in request.form
    do_bdd       = "bdd" in request.form
    scenario_dict = session["scenario"]
    scenario      = _to_scenario(scenario_dict)

    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {"status": "running", "results": [], "steps": {"transform": do_transform, "bdd": do_bdd}}
    session["job_id"] = job_id

    def _worker(job_id: str, scenario: Scenario, do_transform: bool, do_bdd: bool):
        results: list[tuple[bool, str, str]] = []
        try:
            if do_transform:
                ok, detail = _safe_transform(scenario)
                label = "✅ Código limpo salvo" if ok else "❌ Erro na limpeza"
                results.append((ok, label, detail))
            if do_bdd:
                ok, detail = _safe_bdd(scenario)
                label = "✅ Feature gerada" if ok else "❌ Erro no BDD"
                results.append((ok, label, detail))
            _jobs[job_id]["results"] = results
            _jobs[job_id]["status"]  = "done"
        except Exception as exc:
            _jobs[job_id]["results"] = [(False, "❌ Erro inesperado", str(exc))]
            _jobs[job_id]["status"]  = "done"

    threading.Thread(target=_worker, args=(job_id, scenario, do_transform, do_bdd), daemon=True).start()
    return redirect(url_for("processing_wait"))


@app.route("/processing-wait")
def processing_wait():
    if "scenario" not in session:
        return redirect(url_for("home"))
    return render_template("processing_wait.html", scenario=session["scenario"])


@app.route("/api/job-status")
def api_job_status():
    job_id = session.get("job_id")
    if not job_id or job_id not in _jobs:
        return jsonify({"status": "unknown"})
    job = _jobs[job_id]
    if job["status"] != "done":
        return jsonify({"status": "running"})
    # Move resultado para sessão e limpa o job
    session["results"]    = job["results"]
    session["last_steps"] = job["steps"]
    del _jobs[job_id]
    return jsonify({"status": "done"})


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
    return render_template(
        "results.html",
        results=res,
        scenario=scenario,
        has_failure=has_failure,
        last_steps=last_steps,
        suite_scenarios=suite_scenarios,
    )


@app.route("/regression/<plan_name>")
def regression(plan_name: str):
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
                     "back_url": "/"}
    session["job_id"] = job_id

    def _worker(job_id: str, cmd: list, plan: str, evidences_url: str, back_url: str):
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
        _jobs[job_id].update({
            "status":       "done",
            "output":       output,
            "passed":       result.returncode == 0,
            "plan":         plan,
            "evidences_url": evidences_url,
            "back_url":     back_url,
        })

    threading.Thread(
        target=_worker,
        args=(job_id,
              [sys.executable, "-m", "pytest", str(cleaned_dir), "--headed", "-v", "--tb=short"],
              plan_name,
              f"/regression/{plan_name}/evidences",
              "/"),
        daemon=True,
    ).start()
    return redirect(url_for("pytest_wait", label=plan_name))


@app.route("/pytest-wait/<label>")
def pytest_wait(label: str):
    """Tela de espera enquanto o pytest roda em background."""
    return render_template("pytest_wait.html", label=label)


@app.route("/api/pytest-status")
def api_pytest_status():
    """Polling: retorna status do job pytest corrente na sessão."""
    job_id = session.get("job_id")
    if not job_id or job_id not in _jobs:
        return jsonify({"status": "unknown"})
    job = _jobs[job_id]
    if job["status"] != "done":
        return jsonify({"status": "running"})
    # Job concluído — move dados para sessão e limpa
    session["pytest_result"] = {
        "output":        job["output"],
        "passed":        job["passed"],
        "plan":          job["plan"],
        "evidences_url": job.get("evidences_url"),
        "back_url":      job.get("back_url", "/"),
    }
    del _jobs[job_id]
    return jsonify({"status": "done"})


@app.route("/pytest-result")
def pytest_result():
    """Exibe o resultado do pytest após polling."""
    r = session.get("pytest_result")
    if not r:
        return redirect(url_for("home"))
    return render_template(
        "regression.html",
        output=r["output"],
        passed=r["passed"],
        plan=r["plan"],
        evidences_url=r.get("evidences_url"),
        back_url=r.get("back_url", "/"),
    )


@app.route("/regression/<plan_name>/evidences")
def regression_evidences(plan_name: str):
    """Galeria de evidências de uma bateria (SUITE)."""
    # LLM generates: Path(__file__).parent / "evidences"
    # For SUITE, test files live in cleaned/ → evidences land in cleaned/evidences/
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
    scenario = Scenario(name=scenario_name, url="", mode=ExecutionMode.SINGLE)
    if not scenario.clean_path.exists():
        return render_template(
            "home.html",
            plans=_available_plans(),
            scenarios=_available_scenarios(),
            error=f"Teste não encontrado: {scenario.clean_path}",
        )

    job_id = str(_uuid.uuid4())
    _jobs[job_id] = {"status": "running", "kind": "pytest", "plan": scenario_name,
                     "evidences_url": f"/run-test/{scenario_name}/evidences",
                     "back_url": "/"}
    session["job_id"] = job_id

    def _worker(job_id: str, cmd: list, plan: str, evidences_url: str, back_url: str):
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

    threading.Thread(
        target=_worker,
        args=(job_id,
              [sys.executable, "-m", "pytest", str(scenario.clean_path), "--headed", "-v", "--tb=short"],
              scenario_name,
              f"/run-test/{scenario_name}/evidences",
              "/"),
        daemon=True,
    ).start()
    return redirect(url_for("pytest_wait", label=scenario_name))


@app.route("/run-test/<scenario_name>/evidences")
def run_test_evidences(scenario_name: str):
    """Galeria de evidências de um cenário isolado (SINGLE)."""
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


@app.route("/evidence-image")
def evidence_image():
    """Serve uma imagem de evidência de qualquer path no disco."""
    img_path = request.args.get("path", "").strip()
    if not img_path:
        return "path obrigatório", 400
    p = Path(img_path)
    if not p.exists() or not p.is_file():
        return "Não encontrado", 404
    return send_file(str(p.resolve()), mimetype="image/png")


@app.route("/library")
def library():
    return render_template("library.html", library=_evidence_library())


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
    """Alias CORS-friendly para /evidence-image."""
    img_path = request.args.get("path", "").strip()
    if not img_path:
        return _cors(jsonify({"error": "path obrigatório"})), 400
    p = Path(img_path)
    if not p.exists() or not p.is_file():
        return _cors(jsonify({"error": "não encontrado"})), 404
    response = send_file(str(p.resolve()), mimetype="image/png")
    return _cors(response)


@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
