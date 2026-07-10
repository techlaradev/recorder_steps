import re

from orchestrator_flows.domain.scenario import Scenario
from orchestrator_flows.ia_prompting.code_perform_IA import StepTransformer


class ScenarioTransformerService:

    def __init__(
        self,
        transformer_service: StepTransformer,
    ):
        self.transformer_service = transformer_service

    def extract_relevant_code(self, code: str) -> str:
        lines = code.splitlines()

        filtered = [
            line
            for line in lines
            if "page." in line
            and "wait_for_timeout" not in line
        ]

        return "\n".join(filtered).strip()[:3000]

    def normalize_pytest_code(
        self,
        code: str,
        scenario_name: str,
    ) -> str:
        code = code.strip()

        py_name = scenario_name.replace("-", "_")
        expected_function_name = f"test_{py_name}"

        if f"def {expected_function_name}(" in code:
            return code

        function_pattern = r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("

        match = re.search(
            function_pattern,
            code,
        )

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

    def run_transform(self, scenario: Scenario) -> bool:
        print(f"\n🧠 Limpando cenário: {scenario.name}")

        try:
            if not scenario.raw_path.exists():
                print(f"❌ Arquivo não encontrado: {scenario.raw_path}")
                return False

            with scenario.raw_path.open("r", encoding="utf-8") as file:
                code = file.read()

            print("➡️ filtrando código relevante...")

            code_filtered = self.extract_relevant_code(code)

            if not code_filtered:
                print("⚠️ Nenhuma linha relevante encontrada para enviar à IA.")
                return False

            print("➡️ enviando para IA...")

            clean_code = self.transformer_service.transform_to_playwright(
                code_filtered
            )

            clean_code = self.normalize_pytest_code(
                clean_code,
                scenario.name,
            )

            with scenario.clean_path.open("w", encoding="utf-8") as file:
                file.write(clean_code)

            print(f"✅ Código limpo salvo em: {scenario.clean_path}")
            return True

        except Exception as e:
            print(f"❌ Erro na IA: {e}")

            while True:
                option = input(
                    "\n"
                    "[r] tentar novamente\n"
                    "[s] pular cenário\n"
                    "[q] abortar processamento\n"
                    "Escolha: "
                ).strip().lower()

                if option == "r":
                    return self.run_transform(scenario)

                if option == "s":
                    print(f"⏭️ Ignorado: {scenario.name}")
                    return False

                if option == "q":
                    raise

    def process_batch(
        self,
        scenarios: list[Scenario],
    ) -> None:
        if not scenarios:
            print("⚠️ Nenhum cenário para processar.")
            return

        print("\n" + "=" * 60)
        print("🧠 Processando limpeza da bateria")
        print("=" * 60)

        for scenario in scenarios:
            self.run_transform(scenario)

        print("\n✅ Processamento de limpeza finalizado!")