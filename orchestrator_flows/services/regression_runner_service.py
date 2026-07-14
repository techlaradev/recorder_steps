from pathlib import Path
from datetime import datetime

from orchestrator_flows.services.orchestrator import FlowOrchestratorService
from orchestrator_flows.services.printer_service import StructurePrinterService
from orchestrator_flows.services.recorder_service import RecorderService


 def run_regression_flow(self) -> None:
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