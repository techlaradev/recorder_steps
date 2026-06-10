class StepTransformer:
    def __init__(self, ollama_client):
        self.ollama = ollama_client

    def transform_to_playwright(self, code: str) -> str:
        prompt = f"""
Clean and optimize the following Playwright Python script.
Keep only relevant steps and organize clearly:

{code}
"""
        return self.ollama.generate(prompt)