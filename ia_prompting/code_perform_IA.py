from ia_prompting.prompts.transform_playwright import (
    TransformPlaywright
)


class StepTransformer:

    def __init__(self, ollama_client):
        self.ollama = ollama_client

    def transform_to_playwright(
        self,
        code: str
    ) -> str:

        prompt = self._build_prompt(code)

        response = self.ollama.generate(
            prompt
        )

        extracted_code = self._extract_python_code(
            response
        )

        return self._sanitize_playwright_code(
            extracted_code
        )

    def _build_prompt(
        self,
        code: str
    ) -> str:

        return TransformPlaywright.build_prompt(
            code
        )

    def _extract_python_code(
        self,
        response: str
    ) -> str:

        response = response.strip()

        if "```python" in response:
            response = response.split(
                "```python",
                1
            )[1]

            response = response.split(
                "```",
                1
            )[0]

            return response.strip()

        if "```py" in response:
            response = response.split(
                "```py",
                1
            )[1]

            response = response.split(
                "```",
                1
            )[0]

            return response.strip()

        if "```" in response:
            response = response.split(
                "```",
                1
            )[1]

            response = response.split(
                "```",
                1
            )[0]

            return response.strip()

        return response.strip()

    def _sanitize_playwright_code(
        self,
        code: str
    ) -> str:

        code = code.strip()

        forbidden_lines = [
            "import pytest",
            "@pytest.mark.asyncio",
            "@pytest.mark.chrome",
            "@pytest.mark.avoid_setup",
        ]

        lines = code.splitlines()

        cleaned_lines = [
            line
            for line in lines
            if line.strip() not in forbidden_lines
        ]

        code = "\n".join(
            cleaned_lines
        ).strip()

        code = code.replace(
            "from playwright.async_api import Page, expect",
            "from playwright.sync_api import Page, expect"
        )

        code = code.replace(
            "from playwright.async_api import Playwright, expect",
            "from playwright.sync_api import Page, expect"
        )

        code = code.replace(
            "from playwright.async_api import Playwright, async_block",
            "from playwright.sync_api import Page, expect"
        )

        if not code.startswith(
            "from playwright.sync_api import Page, expect"
        ):
            code = (
                "from playwright.sync_api import Page, expect\n\n"
                + code
            )

        return code.strip() + "\n"