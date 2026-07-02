from pathlib import Path
from datetime import datetime
import json


class EvidenceFolderGenerator:

    def __init__(self, base_path="evidence"):
        self.base_path = Path(base_path)

    def create_execution_folder(self, scenario_name: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        execution_folder = (
            self.base_path /
            f"{scenario_name}_{timestamp}"
        )

        screenshots_folder = execution_folder / "screenshots"
        logs_folder = execution_folder / "logs"
        reports_folder = execution_folder / "reports"

        screenshots_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        logs_folder.mkdir(
            exist_ok=True
        )

        reports_folder.mkdir(
            exist_ok=True
        )

        metadata = {
            "scenario": scenario_name,
            "created_at": datetime.now().isoformat(),
            "status": "started"
        }

        metadata_file = (
            execution_folder /
            "execution_info.json"
        )

        with open(
            metadata_file,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                metadata,
                file,
                indent=4,
                ensure_ascii=False
            )

        return execution_folder