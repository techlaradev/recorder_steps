from ia_prompting.prompt_builder import PromptBuilder


class StepTransformer:
    def __init__(self, ollama_client):
        self.ollama = ollama_client
        self.prompt_builder = PromptBuilder()

    def transform_to_playwright(self, code: str) -> str:
        prompt = self.prompt_builder.build_transform_to_pytest_prompt(code)
        response = self.ollama.generate(prompt)
        return self._extract_python_code(response)

    def _extract_python_code(self, response: str) -> str:
        response = response.strip()

        if "```python" in response:
            response = response.split("```python", 1)[1]
            response = response.split("```", 1)[0]
            return response.strip()

        if "```py" in response:
            response = response.split("```py", 1)[1]
            response = response.split("```", 1)[0]
            return response.strip()

        if "```" in response:
            response = response.split("```", 1)[1]
            response = response.split("```", 1)[0]
            return response.strip()

        required_import = "from playwright.sync_api import Page, expect"

        if required_import in response:
            response = response[response.index(required_import):]

        ending_markers = [
            "\nThis test",
            "\nThis code",
            "\nThe test",
            "\nExplanation",
            "\nIt also",
            "\nIt follows",
            "\nThis function",
        ]

        for marker in ending_markers:
            if marker in response:
                response = response.split(marker, 1)[0]

        return response.strip()