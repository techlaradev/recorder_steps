import requests

class OllamaClient:
    def __init__(self, model="qwen2.5-coder:14b"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    def generate(self, prompt):
        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        return response.json()["response"]