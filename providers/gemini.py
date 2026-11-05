import os

from google import genai
from google.genai import types

from .base import Provider


class GeminiProvider(Provider):
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.name = f"gemini:{model}"
        self.model = model
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def ask(self, system: str, prompt: str) -> str:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return resp.text or ""
