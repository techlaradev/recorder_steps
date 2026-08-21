# domain/scenario.py

from dataclasses import dataclass
from pathlib import Path

from orchestrator_flows.domain.execution import ExecutionMode

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
            if not self.plan_name:
                raise ValueError(
                    f"Cenário SUITE '{self.name}' sem plan_name definido."
                )
            return self.base_dir / "test-plans" / self.plan_name

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
        self.scenario_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.clean_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.evidences_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.logs_dir.mkdir(
            parents=True,
            exist_ok=True,
        )