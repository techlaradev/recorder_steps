class Humanizer:
    def __init__(self, ollama_client):
        self.ollama = ollama_client

    def steps_to_bdd(self, code: str) -> str:
        prompt = f"""
Convert the following Playwright script into pure BDD.

Rules:
- Return only the BDD content.
- Do not use markdown.
- Do not use code fences.
- Do not write 'gherkin'.
- Do not write explanations.
- Do not write comments.
- Start directly with Background or Scenario.
- Be concise and objective.

Script:

{code}
"""
        response = self.ollama.generate(prompt)
        return self._clean_bdd(response)

    def _clean_bdd(self, response: str) -> str:
        response = response.strip()

        replacements = [
            "```gherkin",
            "```feature",
            "```",
            "gherkin",
            "Gherkin",
            "Feature:",
        ]

        for item in replacements:
            response = response.replace(item, "")

        lines = []

        for line in response.splitlines():
            line = line.rstrip()

            if not line:
                lines.append("")
                continue

            if line.startswith("#"):
                continue

            if line.lower().startswith("explanation"):
                break

            lines.append(line)

        return "\n".join(lines).strip()