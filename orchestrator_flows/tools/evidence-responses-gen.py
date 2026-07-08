from pathlib import Path


class EvidenceManager:

    def __init__(self, execution_folder):
        self.execution_folder = Path(execution_folder)

        self.screenshots_folder = (
            self.execution_folder /
            "screenshots"
        )

        self.screenshots_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        self.step_counter = 1

    def build_screenshot_path(
        self,
        step_description: str
    ) -> Path:

        safe_name = (
            step_description
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
            .replace("?", "_")
            .replace("*", "_")
            .replace('"', "_")
            .replace("<", "_")
            .replace(">", "_")
            .replace("|", "_")
        )

        screenshot_name = (
            f"{self.step_counter:03d}_{safe_name}.png"
        )

        self.step_counter += 1

        return (
            self.screenshots_folder /
            screenshot_name
        )

    def next_step(
        self,
        step_description: str
    ) -> str:

        return str(
            self.build_screenshot_path(
                step_description
            )
        )