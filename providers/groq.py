import os

from groq import Groq

from .base import Provider


class GroqProvider(Provider):
    def __init__(self, model: str = "openai/gpt-oss-20b"):
        self.name = f"groq:{model}"
        self.model = model
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def ask(self, system: str, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""
