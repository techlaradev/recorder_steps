import subprocess
import time
import requests


class OllamaClient:
    def __init__(self, model="llama3.1"):
        self.model = model
        self.base_url = "http://localhost:11434"
        self.url = f"{self.base_url}/api/generate"

    def is_running(self) -> bool:
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=2
            )
            return response.status_code == 200

        except requests.RequestException:
            return False

    def start(self) -> None:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def ensure_running(self) -> None:
        if self.is_running():
            return

        print("🚀 Iniciando Ollama...")

        self.start()

        for _ in range(15):
            if self.is_running():
                print("✅ Ollama iniciado.")
                return

            time.sleep(1)

        raise RuntimeError(
            "Não foi possível iniciar o Ollama."
        )

    def generate(self, prompt: str) -> str:
        self.ensure_running()

        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=300
        )

        response.raise_for_status()

        return response.json()["response"]