from ia_prompting.prompt_builder import PromptBuilder


class Humanizer:
    def __init__(self, ollama_client):
        self.ollama = ollama_client
        self.prompt_builder = PromptBuilder()

    def steps_to_bdd(self, code: str) -> str:
        prompt = self.prompt_builder.build_generate_bdd_prompt(code)
        response = self.ollama.generate(prompt)
        return self._clean_bdd(response)

    def _clean_bdd(self, response: str) -> str:
        response = response.strip()

        forbidden_tokens = [
            "```gherkin",
            "```feature",
            "```",
            "gherkin",
            "Gherkin"
        ]

        for token in forbidden_tokens:
            response = response.replace(token, "")

        ending_markers = [
            "\nExplanation",
            "\nNotes",
            "\nSummary",
            "\nThis scenario",
            "\nThis feature",
        ]

        for marker in ending_markers:
            if marker in response:
                response = response.split(marker, 1)[0]

        return response.strip()