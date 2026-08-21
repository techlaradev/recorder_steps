"""
client_claude.py — Drop-in replacement for OllamaClient using the Anthropic SDK.

Mesma interface: client.generate(prompt) -> str
Assim StepTransformer e Humanizer funcionam sem nenhuma alteração.
"""

import os

import anthropic


class ClaudeClient:
    """Cliente Claude com a mesma interface pública de OllamaClient.

    Parâmetros
    ----------
    model : str
        Modelo Anthropic a usar. Padrão: claude-haiku-4-5 (rápido e econômico).
        Use "claude-sonnet-5" para maior qualidade se necessário.
    max_tokens : int
        Limite de tokens na resposta. Padrão 4096 — suficiente para código limpo.
    api_key : str | None
        Chave da API. Se None, lê da variável de ambiente ANTHROPIC_API_KEY.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 4096,
        api_key: str | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    # ── interface pública (igual ao OllamaClient) ─────────────────────────────

    def generate(self, prompt: str) -> str:
        """Envia o prompt ao Claude e retorna a resposta em texto."""
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extrai o texto do primeiro bloco de conteúdo
        return message.content[0].text

    # ── stubs de compatibilidade (não fazem nada — API está sempre disponível) ─

    def is_running(self) -> bool:
        """Sempre True: a API Anthropic não precisa ser iniciada localmente."""
        return True

    def ensure_running(self) -> None:
        """No-op: a API está sempre disponível."""
        pass
