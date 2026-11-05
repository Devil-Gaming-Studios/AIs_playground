"""Provider adapters: one `ask(system, prompt)` interface per AI."""
from .base import Provider
from .claude import ClaudeProvider
from .gemini import GeminiProvider
from .groq import GroqProvider

__all__ = ["Provider", "ClaudeProvider", "GeminiProvider", "GroqProvider", "build_providers"]


def build_providers() -> dict[str, Provider]:
    """Map each Round Table role to the AI that plays it."""
    return {
        "planner": ClaudeProvider(),
        "coder": GroqProvider("openai/gpt-oss-20b"),
        "reviewer": GeminiProvider(),
        "tester": GroqProvider("llama-3.1-8b-instant"),
        "judge": ClaudeProvider(),
    }
