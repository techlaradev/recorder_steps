class StepTransformer:
    def __init__(self, ollama_client):
        self.ollama = ollama_client

    def transform_to_playwright(self, code: str) -> str:
        prompt = f"""
    You are a Senior QA Automation Engineer specialized in Playwright Python and pytest-playwright.

    Generate a clean pytest test using the official Playwright style.

    Follow the same style used in the official Playwright examples.

    Example:

    from playwright.sync_api import Page, expect

    def test_example(page: Page):
        page.goto("https://example.com")

        page.get_by_role(
            "link",
            name="Get started"
        ).click()

        expect(
            page.get_by_role(
                "heading",
                name="Installation"
            )
        ).to_be_visible()

    CRITICAL REQUIREMENT

    The generated function MUST ALWAYS have this exact signature:

    def test_<scenario_name>(page: Page):

    VALID:

    def test_login(page: Page):

    INVALID:

    def test_login()

    INVALID:

    def test_login(browser)

    INVALID:

    def test_login(context)

    The page fixture is mandatory.

    The generated code MUST use only the pytest-playwright page fixture.

    Every Playwright interaction MUST use:

    page.goto(...)
    page.locator(...)
    page.get_by_role(...)
    page.get_by_text(...)
    page.get_by_label(...)
    page.get_by_placeholder(...)
    page.get_by_test_id(...)

    OBJECTIVE

    Generate a single executable pytest test.

    RULES

    - Return ONLY Python code.
    - Return exactly one test function.
    - The function name MUST start with test_.
    - The function MUST receive page: Page.
    - Use synchronous Playwright only.
    - Use pytest-playwright page fixture.
    - Keep the original business flow.
    - Remove recorder noise.
    - Remove duplicated actions.
    - Remove unnecessary click() before fill().
    - Keep code simple and readable.
    - Preserve original behavior.
    - Do not invent selectors.
    - Do not invent validations.
    - Do not use markdown.
    - Do not add explanations.
    - Do not add text outside code.

    PLAYWRIGHT OFFICIAL ASSERTION STYLE

    Prefer:

    expect(
        page.get_by_test_id(...)
    ).to_be_visible()

    expect(
        page.get_by_role(...)
    ).to_be_visible()

    expect(
        page.get_by_text(...)
    ).to_be_visible()

    expect(page).to_have_url(...)
    expect(page).to_have_title(...)

    Avoid:

    expect(page.locator("body")).to_contain_text(...)

    Only use body assertions when there is no better business locator available.

    TEXT VALIDATION RULES

    Never validate huge concatenated texts.

    INVALID:

    expect(
        page.get_by_text(
            "Bem-vindo ao pântano, tester!Sessão autenticada..."
        )
    ).to_be_visible()

    Prefer:

    expect(
        page.get_by_text(
            "Bem-vindo ao pântano"
        )
    ).to_be_visible()

    or

    expect(
        page.get_by_role(...)
    ).to_be_visible()

    or

    expect(
        page.get_by_test_id(...)
    ).to_be_visible()

    Validate only small and meaningful business texts.

    CLICK RULES

    Never click huge concatenated texts.

    Prefer selectors in this order:

    1. get_by_test_id(...)
    2. get_by_role(...)
    3. get_by_label(...)
    4. get_by_placeholder(...)
    5. get_by_text(...)

    Use get_by_text only for short and stable business texts.

    IMAGE ACCESSIBILITY RULES

    - Never transform image accessible names into text assertions.
    - If an image exists, validate it with:
    expect(locator).to_be_visible()
    - Do not create text assertions based on alt text or accessible names.

    FORBIDDEN

    - async
    - await
    - asyncio
    - async_playwright
    - sync_playwright
    - browser.launch
    - browser
    - context
    - new_context
    - new_page
    - class
    - helper methods
    - fixture
    - @pytest.fixture
    - generator
    - yield
    - yield from
    - setup
    - teardown
    - markdown
    - explanations
    - import pytest

    INPUT SCRIPT

    {code}
    """

        response = self.ollama.generate(prompt)

        extracted_code = self._extract_python_code(response)

        return self._sanitize_playwright_code(
            extracted_code
        )
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

        return response.strip()

    def _sanitize_playwright_code(self, code: str) -> str:
        code = code.strip()

        forbidden_lines = [
            "import pytest",
            "@pytest.mark.asyncio",
            "@pytest.mark.chrome",
            "@pytest.mark.avoid_setup",
        ]

        lines = code.splitlines()

        cleaned_lines = [
            line for line in lines
            if line.strip() not in forbidden_lines
        ]

        code = "\n".join(cleaned_lines).strip()

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

        code = code.replace(
            "expect(page).to_have_text(",
            'expect(page.locator("body")).to_contain_text('
        )

        code = code.replace(
            "expect(page.url()).to_include(",
            "assert "
        )

        required_header = (
            "from playwright.sync_api import Page, expect\n"
            "from pathlib import Path\n"
            "from datetime import datetime"
        )

        if not code.startswith("from playwright.sync_api import Page, expect"):
            code = f"{required_header}\n\n{code}"

        if "from pathlib import Path" not in code:
            code = code.replace(
                "from playwright.sync_api import Page, expect",
                "from playwright.sync_api import Page, expect\nfrom pathlib import Path"
            )

        if "from datetime import datetime" not in code:
            code = code.replace(
                "from pathlib import Path",
                "from pathlib import Path\nfrom datetime import datetime"
            )

        self._validate_generated_code(code)

        return code.strip()

    def _validate_generated_code(self, code: str) -> None:
        forbidden_patterns = [
            "async def",
            "await ",
            "playwright.async_api",
            "async_playwright",
            "asyncio",
            "anyio",
            "asynccontextmanager",
            "browser.launch",
            "browser.new_page",
            "new_context",
            "new_page",
            "sync_playwright(",
            "import pytest",
            "@pytest.fixture",
            "yield",
            "yield from",
            "def main",
            'if __name__ == "__main__"',
            "class ",
            "expect(page.url()).to_include",
        ]

        for pattern in forbidden_patterns:
            if pattern in code:
                raise ValueError(
                    f"Código inválido gerado pela IA. Padrão proibido encontrado: {pattern}"
                )