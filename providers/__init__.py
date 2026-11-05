"""Provider adapters and role-to-provider configuration."""

from .base import Provider

__all__ = ["Provider", "build_providers"]


def build_providers() -> dict[str, Provider]:
    """Create provider clients only when a run starts."""
    from .claude import ClaudeProvider
    from .gemini import GeminiProvider
    from .groq import GroqProvider

    return {
        "planner": ClaudeProvider(),
        "coder": GroqProvider("openai/gpt-oss-20b"),
        "reviewer": GeminiProvider(),
        "tester": GroqProvider("llama-3.1-8b-instant"),
        "judge": ClaudeProvider(),
    }
