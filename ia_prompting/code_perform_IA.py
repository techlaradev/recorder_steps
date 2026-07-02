class StepTransformer:
    def __init__(self, ollama_client):
        self.ollama = ollama_client

    def transform_to_playwright(self, code: str) -> str:
        prompt = f"""
You are a Senior QA Automation Engineer specialized in Playwright Python and pytest-playwright.

Transform the input Playwright recorder script into a clean and executable pytest test.

OBJECTIVE

Generate a single executable pytest test that can be collected and executed by pytest.

MANDATORY OUTPUT

The output MUST start exactly with:

from playwright.sync_api import Page, expect

The output MUST contain exactly one test function using this structure:

def test_<scenario_name>(page: Page):
    ...

PYTEST COLLECTION RULES

The generated code must be a regular pytest test.

The generated file must be directly executable by:

pytest <file_name>.py

without requiring any additional fixture, class, async runtime, browser initialization, generator, yield statement, or setup code.

NEVER generate:
- yield
- yield from
- fixtures
- @pytest.fixture
- generators
- setup methods
- teardown methods
- custom page fixtures
- browser lifecycle context managers
- class-based tests
- helper methods
- main function
- if __name__ == "__main__"

The test function must execute all actions directly.

Good example:

from playwright.sync_api import Page, expect

def test_login(page: Page):
    ## Open login page
    page.goto("https://example.com")

    ## Fill valid credentials
    page.get_by_test_id("username").fill("tester")
    page.get_by_test_id("password").fill("password")

    ## Submit login form
    page.get_by_test_id("submit").click()

    ## Validate successful login
    expect(page.get_by_test_id("logout-button")).to_be_visible()

Bad example:

def test_login(page: Page):
    yield page

Bad example:

@pytest.fixture
def page_fixture():
    yield page

Bad example:

class TestLogin:
    def test_login(self, page: Page):
        ...

Bad example:

async def test_login(page):
    await page.goto("https://example.com")

RULES

- Return ONLY Python code
- Return exactly one test function
- The function name MUST start with test_
- The function MUST receive page: Page
- Use synchronous Playwright only
- Use pytest-playwright page fixture
- Keep the original business flow
- Remove recorder noise
- Remove duplicated actions
- Remove unnecessary click() before fill()
- Keep code simple and readable
- Use expect() assertions whenever possible
- Generate meaningful test names
- Preserve original behavior
- Do not invent selectors
- Do not invent validations
- Make the generated code easy to convert later into a Gherkin .feature file
- DO NOT use markdown
- DO NOT use ``` or ```python
- DO NOT add explanations
- DO NOT add text before or after the code
- DO NOT add blank text before the import

Never generate:
- comments starting with a single # followed by text
- comments starting with ###
- explanatory comments
- technical comments
- long comments
- comments outside the test function

FORBIDDEN

- async
- await
- asyncio
- async_playwright
- sync_playwright
- Playwright
- browser.launch
- browser
- context
- new_context
- new_page
- class
- helper methods
- def main
- if __name__ == "__main__"
- yield
- yield from
- fixture
- @pytest.fixture
- generator
- setup
- teardown
- docstrings
- markdown
- explanations
- external libraries
- import pytest
- import re
- import time

BDD COMPATIBILITY

Generate actions and comments that clearly represent business behavior and can later be mapped to Given, When, Then steps.

Good:

## Open login page
page.goto(...)

## Fill valid credentials
page.get_by_test_id("username").fill(...)
page.get_by_test_id("password").fill(...)

## Submit login form
page.get_by_test_id("submit").click()

## Validate successful authentication
expect(...).to_be_visible()

Bad:

click_username_field()
execute_login_flow()
process_authentication()
yield page

INPUT SCRIPT

{code}
"""
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