from pathlib import Path

from orchestrator_flows.domain.scenario import Scenario


class StructurePrinterService:

    def print_single_structure(self, scenario: Scenario) -> None:
        print("\n📁 Estrutura criada:")
        print(f"📂 {scenario.root_dir}")
        print(f"   ├── {scenario.name}.py")
        print(f"   ├── test_{scenario.py_name}.py")
        print(f"   ├── {scenario.name}.feature")
        print("   ├── evidences/")
        print("   └── logs/")

    def print_suite_structure(self, plan_root: Path) -> None:
        print("\n📁 Estrutura da bateria:")
        print(f"📂 {plan_root}")
        print("   ├── scenarios/")
        print("   ├── cleaned/")
        print("   ├── evidences/")
        print("   ├── logs/")
        print("   └── arquivo .feature consolidado")