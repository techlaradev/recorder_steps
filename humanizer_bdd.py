class Humanizer:
    def __init__(self, ollama_client):
        self.ollama = ollama_client

    def steps_to_bdd(self, code: str) -> str:
        prompt = f"""
Convert the following Playwright script into BDD (Gherkin format):

{code}

Use:
Given / When / Then
"""
        return self.ollama.generate(prompt)