from urllib.parse import urlparse

from orchestrator_flows.domain.execution import ExecutionMode
from orchestrator_flows.domain.scenario import Scenario
from orchestrator_flows.utils.slugify import slugify


class CliService:

    def ask_yes_no(self, message: str) -> bool:
        print(message)

        value = input(
            "Digite 's' para sim ou 'n' para não: "
        ).strip().lower()

        while value not in {"s", "n"}:
            value = input(
                "Digite apenas 's' ou 'n': "
            ).strip().lower()

        return value == "s"

    def is_valid_url(
        self,
        url: str,
    ) -> bool:

        if (
            url.startswith("localhost:")
            or url.startswith("127.0.0.1:")
        ):
            return True

        try:
            parsed = urlparse(url)

            return (
                parsed.scheme in {"http", "https"}
                and bool(parsed.netloc)
            )

        except Exception:
            return False

    def ask_url(
        self,
        message: str,
    ) -> str:

        while True:
            url = input(message).strip()

            if self.is_valid_url(url):
                return url

            print("\n❌ URL inválida.")
            print("Exemplos válidos:")
            print("  https://google.com")
            print("  https://www.youtube.com/watch?v=abc")
            print("  localhost:3000")
            print("  127.0.0.1:8000")

    def ask_execution_mode(
        self,
    ) -> tuple[
        ExecutionMode,
        str | None,
        str | None,
    ]:

        print("\n🎯 Como deseja executar?")
        print("1 - Teste isolado")
        print("2 - Bateria de testes")
        print("3 - Reprocessar cenário existente")
        print("4 - Regressivo de testes")

        option = input(
            "\nEscolha 1, 2, 3 ou 4: "
        ).strip()

        while option not in {"1", "2", "3", "4"}:
            option = input(
                "Escolha apenas 1, 2, 3 ou 4: "
            ).strip()

        if option == "1":
            return (
                ExecutionMode.SINGLE,
                None,
                None,
            )

        if option == "3":
            return (
                ExecutionMode.REPROCESS,
                None,
                None,
            )
        if option == "4":
            return (
                ExecutionMode.REGRESSION,
                None,
                None,
            )

        plan_name = input(
            "\nDigite o nome da bateria/test plan: "
        ).strip()

        while not plan_name:
            plan_name = input(
                "Digite um nome válido: "
            ).strip()

        plan_name = slugify(plan_name)

        print("\n⚠️ Modo bateria selecionado")
        print("⚠️ A URL será reutilizada em todos os cenários")

        shared_url = self.ask_url(
            "\nDigite a URL base da bateria: "
        )

        return (
            ExecutionMode.SUITE,
            plan_name,
            shared_url,
        )

    def ask_single_scenario(
        self,
    ) -> Scenario | None:

        name = input(
            "\nDigite o nome do teste isolado (ENTER para sair): "
        ).strip()

        if not name:
            return None

        name = slugify(name)

        url = self.ask_url(
            "Digite a URL para iniciar: "
        )

        return Scenario(
            name=name,
            url=url,
            mode=ExecutionMode.SINGLE,
        )

    def ask_suite_scenario(
        self,
        plan_name: str,
        shared_url: str,
    ) -> Scenario | None:

        name = input(
            "\nDigite o nome do cenário (ENTER para finalizar): "
        ).strip()

        if not name:
            return None

        name = slugify(name)

        print(
            f"🔗 URL compartilhada da bateria: {shared_url}"
        )

        return Scenario(
            name=name,
            url=shared_url,
            mode=ExecutionMode.SUITE,
            plan_name=plan_name,
        )

    def ask_reprocess_scenario_name(
        self,
    ) -> str | None:

        scenario_name = input(
            "\nDigite o nome do cenário existente: "
        ).strip()

        if not scenario_name:
            return None

        return slugify(
            scenario_name
        )
        
    def ask_regression_scenario_name(
        self,
    ) -> str | None:

        scenario_name = input(
            "\nDigite o nome do plano de teste para regressivo: "
        ).strip()

        if not scenario_name:
            return None

        return slugify(
            scenario_name
        )
        