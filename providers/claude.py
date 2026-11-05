import os

import anthropic

from .base import Provider


class ClaudeProvider(Provider):
    def __init__(self, model: str = "claude-sonnet-5-5"):
        self.name = f"claude:{model}"
        self.model = model
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def ask(self, system: str, prompt: str) -> str:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
