from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import ia_prompting.prompts.humanizer_bdd as humanizer
import ia_prompting.code_perform_IA as transformer
import ia_prompting.client_ollama as ollama


class ExecutionMode(Enum):
    SINGLE = "single"
    SUITE = "suite"

@dataclass
class Scenario:
    name: str
    url: str
    mode: ExecutionMode
    plan_name: str | None = None
    base_dir: Path = Path("flows")

    @property
    def py_name(self) -> str:
        return self.name.replace("-", "_")

    @property
    def root_dir(self) -> Path:
        if self.mode == ExecutionMode.SUITE:
            return self.base_dir / "test-plans" / str(self.plan_name)

        return self.base_dir / "unity-test" / self.name

    @property
    def scenario_dir(self) -> Path:
        if self.mode == ExecutionMode.SUITE:
            return self.root_dir / "scenarios" / self.name

        return self.root_dir

    @property
    def raw_path(self) -> Path:
        return self.scenario_dir / f"{self.name}.py"

    @property
    def clean_path(self) -> Path:
        if self.mode == ExecutionMode.SUITE:
            return self.root_dir / "cleaned" / f"test_{self.py_name}.py"

        return self.root_dir / f"test_{self.py_name}.py"

    @property
    def feature_path(self) -> Path:
        if self.mode == ExecutionMode.SUITE:
            return self.root_dir / f"{self.plan_name}.feature"

        return self.root_dir / f"{self.name}.feature"

    @property
    def evidences_dir(self) -> Path:
        if self.mode == ExecutionMode.SUITE:
            return self.root_dir / "evidences" / self.name

        return self.root_dir / "evidences"

    @property
    def logs_dir(self) -> Path:
        if self.mode == ExecutionMode.SUITE:
            return self.root_dir / "logs" / self.name

        return self.root_dir / "logs"

    def ensure_dirs(self) -> None:
        self.scenario_dir.mkdir(parents=True, exist_ok=True)
        self.clean_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidences_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


def ask_yes_no(message: str) -> bool:
    print(message)
    value = input("Digite 's' para sim ou 'n' para não: ").strip().lower()

    while value not in {"s", "n"}:
        value = input("Digite apenas 's' ou 'n': ").strip().lower()

    return value == "s"


def ask_execution_mode() -> tuple[ExecutionMode, str | None, str | None]:
    print("\n🎯 Como deseja executar?")
    print("1 - Teste isolado")
    print("2 - Bateria de testes")

    option = input("Escolha 1 ou 2: ").strip()

    while option not in {"1", "2"}:
        option = input("Escolha apenas 1 ou 2: ").strip()

    if option == "1":
        return ExecutionMode.SINGLE, None, None

    plan_name = input("\nDigite o nome da bateria/test plan: ").strip()

    while not plan_name:
        plan_name = input("Digite um nome válido para a bateria/test plan: ").strip()

    plan_name = slugify(plan_name)

    print("\n⚠️ Modo bateria selecionado.")
    print("⚠️ A URL informada será reutilizada para todos os cenários desta bateria.")
    print("⚠️ Ela não poderá ser alterada durante esta execução.")

    shared_url = input("\nDigite a URL base da bateria: ").strip()

    while not shared_url:
        shared_url = input("Digite uma URL válida: ").strip()

    return ExecutionMode.SUITE, plan_name, shared_url


def ask_single_scenario() -> Scenario | None:
    name = input("\nDigite o nome do teste isolado (ENTER para sair): ").strip()

    if not name:
        return None

    name = slugify(name)

    url = input("Digite a URL para iniciar: ").strip()

    while not url:
        url = input("Digite uma URL válida: ").strip()

    return Scenario(
        name=name,
        url=url,
        mode=ExecutionMode.SINGLE,
    )


def ask_suite_scenario(plan_name: str, shared_url: str) -> Scenario | None:
    name = input("\nDigite o nome do cenário (ENTER para finalizar gravações): ").strip()

    if not name:
        return None

    name = slugify(name)

    print(f"🔗 URL compartilhada da bateria: {shared_url}")

    return Scenario(
        name=name,
        url=shared_url,
        mode=ExecutionMode.SUITE,
        plan_name=plan_name,
    )


def run_codegen(scenario: Scenario) -> bool:
    try:
        print("\n➡️ Abrindo Playwright Codegen...")
        print("👉 Execute o fluxo no navegador")
        print("👉 Quando terminar, volte aqui e pressione ENTER")
        print(f"📁 Arquivo será salvo em: {scenario.raw_path}\n")

        cmd = [
            sys.executable,
            "-m",
            "playwright",
            "codegen",
            "--target",
            "python",
            "-o",
            str(scenario.raw_path),
            scenario.url,
        ]

        process = subprocess.Popen(cmd)

        input("\n👉 Pressione ENTER para encerrar o recorder...")

        print("🔪 Encerrando Playwright...")

        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("⚠️ Forçando encerramento...")
            process.kill()
            process.wait()

        print("✅ Codegen finalizado!")
        return True

    except Exception as e:
        print(f"❌ Erro ao rodar Playwright: {e}")
        return False


def extract_relevant_code(code: str) -> str:
    lines = code.splitlines()

    filtered = [
        line for line in lines
        if "page." in line and "wait_for_timeout" not in line
    ]

    return "\n".join(filtered).strip()[:3000]

def normalize_pytest_code(code: str, scenario_name: str) -> str:
    code = code.strip()

    py_name = scenario_name.replace("-", "_")
    expected_function_name = f"test_{py_name}"

    if f"def {expected_function_name}(" in code:
        return code

    function_pattern = r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("

    match = re.search(function_pattern, code)

    if match:
        current_function_name = match.group(1)

        if not current_function_name.startswith("test_"):
            code = re.sub(
                function_pattern,
                f"def {expected_function_name}(",
                code,
                count=1,
            )

    return code

def run_ia_transform(
    scenario: Scenario,
    transformer_service: transformer.StepTransformer,
) -> bool:
    print(f"\n🧠 Limpando cenário: {scenario.name}")

    try:
        if not scenario.raw_path.exists():
            print(f"❌ Arquivo não encontrado: {scenario.raw_path}")
            return False

        with scenario.raw_path.open("r", encoding="utf-8") as f:
            code = f.read()

        print("➡️ filtrando código relevante...")

        code_filtered = extract_relevant_code(code)

        if not code_filtered:
            print("⚠️ Nenhuma linha relevante encontrada para enviar à IA.")
            return False

        print("➡️ enviando para IA...")

        clean_code = transformer_service.transform_to_playwright(code_filtered)
        clean_code = normalize_pytest_code(clean_code, scenario.name)

        with scenario.clean_path.open("w", encoding="utf-8") as f:
            f.write(clean_code)

        print(f"✅ Código limpo salvo em: {scenario.clean_path}")
        return True

    except Exception as e:
        print(f"❌ Erro na IA: {e}")
        return False


def process_clean_batch(
    scenarios: list[Scenario],
    transformer_service: transformer.StepTransformer,
) -> None:
    if not scenarios:
        print("⚠️ Nenhum cenário para processar.")
        return

    print("\n" + "=" * 60)
    print("🧠 Processando limpeza da bateria")
    print("=" * 60)

    for scenario in scenarios:
        run_ia_transform(
            scenario,
            transformer_service,
        )

    print("\n✅ Processamento de limpeza finalizado!")


def build_combined_code(scenarios: list[Scenario]) -> str:
    parts = []

    for scenario in scenarios:
        source_path = scenario.clean_path if scenario.clean_path.exists() else scenario.raw_path

        if not source_path.exists():
            print(f"⚠️ Arquivo ignorado, não encontrado: {source_path}")
            continue

        with source_path.open("r", encoding="utf-8") as f:
            code = f.read().strip()

        if not code:
            print(f"⚠️ Arquivo ignorado, conteúdo vazio: {source_path}")
            continue

        part = f"""
SCENARIO: {scenario.name}

CODE:
{code}
""".strip()

        parts.append(part)

    return "\n\n---\n\n".join(parts).strip()


def clean_bdd_output(response: str) -> str:
    response = response.strip()

    forbidden_tokens = [
        "```gherkin",
        "```feature",
        "```",
        "gherkin",
        "Gherkin",
    ]

    for token in forbidden_tokens:
        response = response.replace(token, "")

    ending_markers = [
        "\nExplanation",
        "\nNotes",
        "\nSummary",
        "\nThis scenario",
        "\nThis feature",
    ]

    for marker in ending_markers:
        if marker in response:
            response = response.split(marker, 1)[0]

    return response.strip()


def ensure_feature_header(
    bdd: str,
    title: str,
) -> str:
    bdd = clean_bdd_output(bdd)

    if bdd.lower().startswith("feature:"):
        return bdd

    return f"Feature: {title}\n\n{bdd}".strip()


def generate_single_bdd(
    scenario: Scenario,
    humanizer_service: humanizer.Humanizer,
) -> bool:
    print(f"\n📄 Gerando BDD do teste isolado: {scenario.name}")

    try:
        source_path = scenario.clean_path if scenario.clean_path.exists() else scenario.raw_path

        if not source_path.exists():
            print(f"❌ Arquivo não encontrado: {source_path}")
            return False

        with source_path.open("r", encoding="utf-8") as f:
            code = f.read()

        bdd = humanizer_service.steps_to_bdd(code)
        title = scenario.name.replace("-", " ").title()
        bdd = ensure_feature_header(bdd, title)

        with scenario.feature_path.open("w", encoding="utf-8") as f:
            f.write(bdd)

        print(f"✅ BDD salvo em: {scenario.feature_path}")
        return True

    except Exception as e:
        print(f"❌ Erro ao gerar BDD: {e}")
        return False


def generate_suite_bdd(
    scenarios: list[Scenario],
    plan_name: str,
    humanizer_service: humanizer.Humanizer,
) -> bool:
    print("\n📄 Gerando BDD consolidado da bateria...")

    try:
        if not scenarios:
            print("⚠️ Nenhum cenário encontrado para gerar BDD.")
            return False

        combined_code = build_combined_code(scenarios)

        if not combined_code:
            print("⚠️ Nenhum código válido encontrado para enviar à IA.")
            return False

        print("➡️ enviando todos os cenários para IA...")

        bdd = humanizer_service.steps_to_bdd(combined_code)

        title = plan_name.replace("-", " ").title()
        bdd = ensure_feature_header(bdd, title)

        feature_path = scenarios[0].feature_path

        with feature_path.open("w", encoding="utf-8") as f:
            f.write(bdd)

        print(f"✅ Feature consolidada salva em: {feature_path}")
        return True

    except Exception as e:
        print(f"❌ Erro ao gerar BDD consolidado: {e}")
        return False


def print_single_structure(scenario: Scenario) -> None:
    print("\n📁 Estrutura criada:")
    print(f"📂 {scenario.root_dir}")
    print(f"   ├── {scenario.py_name}.py")
    print(f"   ├── test_{scenario.py_name}.py")
    print(f"   ├── {scenario.name}.feature")
    print("   ├── evidences/")
    print("   └── logs/")


def print_suite_structure(plan_root: Path) -> None:
    print("\n📁 Estrutura da bateria:")
    print(f"📂 {plan_root}")
    print("   ├── scenarios/")
    print("   ├── cleaned/")
    print("   ├── evidences/")
    print("   ├── logs/")
    print("   └── arquivo .feature consolidado")


def record_single_scenario() -> Scenario | None:
    scenario = ask_single_scenario()

    if scenario is None:
        print("\n👋 Saindo...")
        return None

    scenario.ensure_dirs()
    print_single_structure(scenario)

    if not run_codegen(scenario):
        return None

    print("\n✅ Gravação finalizada!")
    return scenario


def record_suite_scenarios(
    plan_name: str,
    shared_url: str,
) -> list[Scenario]:
    scenarios = []
    plan_root = Path("flows") / "test-plans" / plan_name

    print("\n🧪 Bateria iniciada")
    print(f"📦 Test plan: {plan_name}")
    print(f"🔗 URL fixa: {shared_url}")
    print_suite_structure(plan_root)

    while True:
        scenario = ask_suite_scenario(
            plan_name=plan_name,
            shared_url=shared_url,
        )

        if scenario is None:
            break

        scenario.ensure_dirs()

        print("\n📄 Cenário:")
        print(f"📌 Nome     : {scenario.name}")
        print(f"📄 Raw      : {scenario.raw_path}")
        print(f"📄 Clean    : {scenario.clean_path}")
        print(f"📂 Evidence : {scenario.evidences_dir}")
        print(f"📂 Logs     : {scenario.logs_dir}")

        if run_codegen(scenario):
            scenarios.append(scenario)
            print(f"\n✅ Cenário gravado: {scenario.name}")
        else:
            print(f"\n⚠️ Cenário não foi adicionado à bateria: {scenario.name}")

    print("\n✅ Gravações da bateria finalizadas!")
    print(f"📌 Total de cenários gravados: {len(scenarios)}")

    return scenarios


def run_single_flow(
    scenario: Scenario,
    transformer_service: transformer.StepTransformer,
    humanizer_service: humanizer.Humanizer,
) -> None:
    if ask_yes_no("\n🧠 Deseja limpar o código com IA?"):
        run_ia_transform(
            scenario,
            transformer_service,
        )

    if ask_yes_no("\n📄 Deseja gerar BDD?"):
        generate_single_bdd(
            scenario,
            humanizer_service,
        )

    print("\n✅ Teste isolado finalizado!")
    print(f"📂 Pasta: {scenario.root_dir}")


def run_suite_flow(
    scenarios: list[Scenario],
    plan_name: str,
    transformer_service: transformer.StepTransformer,
    humanizer_service: humanizer.Humanizer,
) -> None:
    if not scenarios:
        print("\n⚠️ Nenhum cenário foi gravado.")
        return

    if ask_yes_no("\n🧠 Deseja limpar todos os cenários da bateria com IA?"):
        process_clean_batch(
            scenarios,
            transformer_service,
        )

    if ask_yes_no("\n📄 Deseja gerar o BDD consolidado da bateria?"):
        generate_suite_bdd(
            scenarios,
            plan_name,
            humanizer_service,
        )

    plan_root = Path("flows") / "test-plans" / plan_name

    print("\n✅ Bateria finalizada!")
    print(f"📂 Pasta da bateria: {plan_root}")
    print(f"📄 Feature consolidada: {plan_root / f'{plan_name}.feature'}")


def main() -> None:
    print("=" * 70)
    print("🐞 Test Plan Orchestrator")
    print("=" * 70)

    ollama_client = ollama.OllamaClient(
        model="mistral:7b-instruct"
    )

    transformer_service = transformer.StepTransformer(
        ollama_client
    )

    humanizer_service = humanizer.Humanizer(
        ollama_client
    )

    mode, plan_name, shared_url = ask_execution_mode()

    if mode == ExecutionMode.SINGLE:
        scenario = record_single_scenario()

        if scenario is None:
            return

        run_single_flow(
            scenario,
            transformer_service,
            humanizer_service,
        )

        return

    if plan_name is None or shared_url is None:
        print("❌ Dados da bateria inválidos.")
        return

    scenarios = record_suite_scenarios(
        plan_name=plan_name,
        shared_url=shared_url,
    )

    run_suite_flow(
        scenarios,
        plan_name,
        transformer_service,
        humanizer_service,
    )


if __name__ == "__main__":
    main()