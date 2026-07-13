class TransformPlaywright:

    ROLE = """
You are a Senior QA Automation Engineer specialized in Playwright Python and pytest-playwright.
"""

    OBJECTIVE = """
OBJECTIVE

Generate a single executable pytest test compatible with pytest-playwright.

The generated test must include evidence screenshots for business checkpoints.
"""

    EXAMPLE = """
Generate a clean pytest test using the official Playwright style.

Example:

from playwright.sync_api import Page, expect

def test_example(page: Page):
    ...
"""

    SIGNATURE_RULES = """
CRITICAL REQUIREMENT

The generated function MUST ALWAYS have this exact signature:

def test_<scenario_name>(page: Page):
"""

    RULES = """
RULES

- Return ONLY Python code
- Return exactly one test function
- Use page: Page
...
"""

    ASSERTIONS = """
PLAYWRIGHT OFFICIAL ASSERTION STYLE

Prefer:
NEVER create selectors, test ids, roles, text, URLs or assertions
that do not exist in the input script.
...
"""

    CLICK_RULES = """
CLICK RULES

Prefer selectors in this order:

1. get_by_test_id(...)
2. get_by_role(...)
...
"""

    FORBIDDEN = """
FORBIDDEN

- async
- await
- sync_playwright
...
"""

    EVIDENCES = """
EVIDENCE RULES

Screenshots are mandatory.

The generated test MUST capture evidence screenshots during execution.

Use page.screenshot() after important business actions and validations.

At minimum capture:

- Initial page state
- After navigation
- After form submission
- After important business transitions
- Final successful state

Screenshot filenames must be descriptive and readable.

Examples:

page.screenshot(
    path="evidences/01_home_page.png"
)

page.screenshot(
    path="evidences/02_login_filled.png"
)

page.screenshot(
    path="evidences/03_authenticated_area.png"
)

Do not generate screenshots on every action.

Capture screenshots only on meaningful business checkpoints.

Keep the screenshots aligned with the business flow.
"""

    @classmethod
    def build_prompt(cls, code: str) -> str:
        return f"""
{cls.ROLE}

{cls.EXAMPLE}

{cls.SIGNATURE_RULES}

{cls.RULES}

{cls.ASSERTIONS}

{cls.CLICK_RULES}

{cls.FORBIDDEN}

{cls.EVIDENCES}

{cls.OBJECTIVE}

INPUT SCRIPT

{code}
"""