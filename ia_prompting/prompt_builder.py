from pathlib import Path


class PromptBuilder:
    def __init__(self):
        self.prompts_dir = Path(__file__).parent / "prompts"

    def build_transform_to_pytest_prompt(self, code: str) -> str:
        return self._build_prompt(
            file_name="transform_to_pytest.txt",
            input_content=code
        )

    def build_generate_bdd_prompt(self, code: str) -> str:
        return self._build_prompt(
            file_name="generate_bdd.txt",
            input_content=code
        )

    def build_generate_steps_prompt(self, feature: str) -> str:
        return self._build_prompt(
            file_name="generate_steps.txt",
            input_content=feature
        )

    def _build_prompt(
        self,
        file_name: str,
        input_content: str
    ) -> str:
        template_path = self.prompts_dir / file_name

        with template_path.open("r", encoding="utf-8") as file:
            template = file.read()

        return template.replace(
            "{{INPUT_SCRIPT}}",
            input_content
        )