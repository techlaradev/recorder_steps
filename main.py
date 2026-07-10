import orchestrator_flows.flow_design.client_ollama as ollama
import ia_prompting.code_perform_IA as transformer
import ia_prompting.prompts.humanizer_bdd as humanizer

from orchestrator_flows.flow_design.CLI_render import CliService
from orchestrator_flows.services.bdd_service import BddGeneratorService
from orchestrator_flows.services.orchestrator import FlowOrchestratorService
from orchestrator_flows.services.printer_service import StructurePrinterService
from orchestrator_flows.services.recorder_service import RecorderService
from orchestrator_flows.services.scenario_transformer_service import (
    ScenarioTransformerService,
)


def main() -> None:
    
    
    
    print("=" * 70)
    print("🐞 Test Plan Orchestrator")
    print("=" * 70)

    ollama_client = ollama.OllamaClient()

    transformer_service = transformer.StepTransformer(
        ollama_client
    )

    humanizer_service = humanizer.Humanizer(
        ollama_client
    )

    cli = CliService()

    structure_printer = StructurePrinterService()

    recorder = RecorderService(
        cli=cli,
        structure_printer=structure_printer,
    )

    scenario_transformer = (
        ScenarioTransformerService(
            transformer_service=transformer_service,
        )
    )

    bdd_generator = BddGeneratorService(
        humanizer_service=humanizer_service,
    )

    orchestrator = FlowOrchestratorService(
        cli=cli,
        recorder=recorder,
        transformer=scenario_transformer,
        bdd_generator=bdd_generator,
    )

    orchestrator.run()


if __name__ == "__main__":
    main()