from pathlib import Path

from orchestrator_flows.domain.execution import ExecutionMode
from orchestrator_flows.domain.scenario import Scenario
from orchestrator_flows.flow_design.CLI_render import CliService
from orchestrator_flows.services.recorder_service import RecorderService
from orchestrator_flows.services.scenario_transformer_service import ScenarioTransformerService
from orchestrator_flows.services.bdd_service import BddGeneratorService


class FlowOrchestratorService:

    def __init__(
        self,
        cli: CliService,
        recorder: RecorderService,
        transformer: ScenarioTransformerService,
        bdd_generator: BddGeneratorService,
    ):
        self.cli = cli
        self.recorder = recorder
        self.transformer = transformer
        self.bdd_generator = bdd_generator

    def run(self) -> None:
        mode, plan_name, shared_url = self.cli.ask_execution_mode()

        if mode == ExecutionMode.REPROCESS:
            self.run_reprocess_flow()
            return

        if mode == ExecutionMode.SINGLE:
            scenario = self.recorder.record_single_scenario()

            if scenario is None:
                return

            self.run_single_flow(scenario)
            return

        if plan_name is None or shared_url is None:
            print("❌ Dados da bateria inválidos.")
            return

        scenarios = self.recorder.record_suite_scenarios(
            plan_name=plan_name,
            shared_url=shared_url,
        )

        self.run_suite_flow(
            scenarios=scenarios,
            plan_name=plan_name,
        )

    def run_single_flow(
        self,
        scenario: Scenario,
    ) -> None:
        if self.cli.ask_yes_no("\n🧠 Deseja limpar o código com IA?"):
            self.transformer.run_transform(scenario)

        if self.cli.ask_yes_no("\n📄 Deseja gerar BDD?"):
            self.bdd_generator.generate_single(scenario)

        print("\n✅ Teste isolado finalizado!")
        print(f"📂 Pasta: {scenario.root_dir}")

    def run_suite_flow(
        self,
        scenarios: list[Scenario],
        plan_name: str,
    ) -> None:
        if not scenarios:
            print("\n⚠️ Nenhum cenário foi gravado.")
            return

        if self.cli.ask_yes_no(
            "\n🧠 Deseja limpar todos os cenários da bateria com IA?"
        ):
            self.transformer.process_batch(scenarios)

        if self.cli.ask_yes_no(
            "\n📄 Deseja gerar o BDD consolidado da bateria?"
        ):
            self.bdd_generator.generate_suite(
                scenarios=scenarios,
                plan_name=plan_name,
            )

        plan_root = Path("flows") / "test-plans" / plan_name

        print("\n✅ Bateria finalizada!")
        print(f"📂 Pasta da bateria: {plan_root}")
        print(f"📄 Feature consolidada: {plan_root / f'{plan_name}.feature'}")

    def run_reprocess_flow(self) -> None:
        scenario_name = self.cli.ask_reprocess_scenario_name()

        if scenario_name is None:
            return

        scenario = Scenario(
            name=scenario_name,
            url="",
            mode=ExecutionMode.SINGLE,
        )

        if not scenario.raw_path.exists():
            print(
                f"❌ Cenário não encontrado:\n"
                f"{scenario.raw_path}"
            )
            return

        success = self.transformer.run_transform(scenario)

        if not success:
            return

        self.bdd_generator.generate_single(scenario)