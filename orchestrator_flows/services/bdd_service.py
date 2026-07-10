from orchestrator_flows.domain.scenario import Scenario
from orchestrator_flows.ia_prompting.prompts.humanizer_bdd import Humanizer


class BddGeneratorService:

    def __init__(
        self,
        humanizer_service: Humanizer,
    ):
        self.humanizer_service = humanizer_service

    def build_combined_code(
        self,
        scenarios: list[Scenario],
    ) -> str:
        parts = []

        for scenario in scenarios:
            source_path = (
                scenario.clean_path
                if scenario.clean_path.exists()
                else scenario.raw_path
            )

            if not source_path.exists():
                print(f"⚠️ Arquivo ignorado, não encontrado: {source_path}")
                continue

            with source_path.open("r", encoding="utf-8") as file:
                code = file.read().strip()

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

    def clean_bdd_output(self, response: str) -> str:
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
        self,
        bdd: str,
        title: str,
    ) -> str:
        bdd = self.clean_bdd_output(bdd)

        if bdd.lower().startswith("feature:"):
            return bdd

        return f"Feature: {title}\n\n{bdd}".strip()

    def generate_single(
        self,
        scenario: Scenario,
    ) -> bool:
        print(f"\n📄 Gerando BDD do teste isolado: {scenario.name}")

        try:
            source_path = (
                scenario.clean_path
                if scenario.clean_path.exists()
                else scenario.raw_path
            )

            if not source_path.exists():
                print(f"❌ Arquivo não encontrado: {source_path}")
                return False

            with source_path.open("r", encoding="utf-8") as file:
                code = file.read()

            bdd = self.humanizer_service.steps_to_bdd(code)

            title = scenario.name.replace("-", " ").title()

            bdd = self.ensure_feature_header(
                bdd,
                title,
            )

            with scenario.feature_path.open("w", encoding="utf-8") as file:
                file.write(bdd)

            print(f"✅ BDD salvo em: {scenario.feature_path}")
            return True

        except Exception as e:
            print(f"❌ Erro ao gerar BDD: {e}")
            return False

    def generate_suite(
        self,
        scenarios: list[Scenario],
        plan_name: str,
    ) -> bool:
        print("\n📄 Gerando BDD consolidado da bateria...")

        try:
            if not scenarios:
                print("⚠️ Nenhum cenário encontrado para gerar BDD.")
                return False

            combined_code = self.build_combined_code(
                scenarios
            )

            if not combined_code:
                print("⚠️ Nenhum código válido encontrado para enviar à IA.")
                return False

            print("➡️ enviando todos os cenários para IA...")

            bdd = self.humanizer_service.steps_to_bdd(
                combined_code
            )

            title = plan_name.replace("-", " ").title()

            bdd = self.ensure_feature_header(
                bdd,
                title,
            )

            feature_path = scenarios[0].feature_path

            with feature_path.open("w", encoding="utf-8") as file:
                file.write(bdd)

            print(f"✅ Feature consolidada salva em: {feature_path}")
            return True

        except Exception as e:
            print(f"❌ Erro ao gerar BDD consolidado: {e}")
            return False