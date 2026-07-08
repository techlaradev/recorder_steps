# services/recorder_service.py

import subprocess
import sys
from pathlib import Path

from orchestrator_flows.domain.scenario import Scenario

from orchestrator_flows.services.printer_service import (
    StructurePrinterService,
)

from orchestrator_flows.flow_design.CLI_render import CliService


class RecorderService:
    def __init__(
        self,
        cli: CliService,
        structure_printer: StructurePrinterService,
    ):
        self.cli = cli
        self.structure_printer = structure_printer

    def run_codegen(
        self,
        scenario: Scenario,
    ) -> bool:
        try:
            print("\n➡️ Abrindo Playwright Codegen...")
            print("👉 Execute o fluxo no navegador")
            print(
                "👉 Quando terminar, volte aqui e pressione ENTER"
            )
            print(
                f"📁 Arquivo será salvo em: "
                f"{scenario.raw_path}\n"
            )

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

            input(
                "\n👉 Pressione ENTER para encerrar o recorder..."
            )

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
            print(
                f"❌ Erro ao rodar Playwright: {e}"
            )
            return False

    def record_single_scenario(
        self,
    ) -> Scenario | None:

        scenario = self.cli.ask_single_scenario()

        if scenario is None:
            print("\n👋 Saindo...")
            return None

        scenario.ensure_dirs()

        self.structure_printer.print_single_structure(
            scenario
        )

        if not self.run_codegen(scenario):
            return None

        print("\n✅ Gravação finalizada!")

        return scenario

    def record_suite_scenarios(
        self,
        plan_name: str,
        shared_url: str,
    ) -> list[Scenario]:
        scenarios: list[Scenario] = []

        plan_root = (
            Path("flows")
            / "test-plans"
            / plan_name
        )

        print("\n🧪 Bateria iniciada")
        print(f"📦 Test plan: {plan_name}")
        print(f"🔗 URL fixa: {shared_url}")

        self.structure_printer.print_suite_structure(
            plan_root
        )

        while True:

            scenario = self.cli.ask_suite_scenario(
                plan_name=plan_name,
                shared_url=shared_url,
            )

            if scenario is None:
                break

            scenario.ensure_dirs()

            print("\n📄 Cenário:")
            print(
                f"📌 Nome     : {scenario.name}"
            )
            print(
                f"📄 Raw      : {scenario.raw_path}"
            )
            print(
                f"📄 Clean    : {scenario.clean_path}"
            )
            print(
                f"📂 Evidence : {scenario.evidences_dir}"
            )
            print(
                f"📂 Logs     : {scenario.logs_dir}"
            )

            if self.run_codegen(scenario):

                scenarios.append(
                    scenario
                )

                print(
                    f"\n✅ Cenário gravado: "
                    f"{scenario.name}"
                )

            else:
                print(
                    "\n⚠️ Cenário não foi "
                    f"adicionado à bateria: "
                    f"{scenario.name}"
                )

        print(
            "\n✅ Gravações da bateria finalizadas!"
        )

        print(
            f"📌 Total de cenários gravados: "
            f"{len(scenarios)}"
        )

        return scenarios