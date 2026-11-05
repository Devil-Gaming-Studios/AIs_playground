from abc import ABC, abstractmethod


class Provider(ABC):
    """Common interface so the orchestrator never cares which AI it is talking to."""

    name: str = "provider"

    @abstractmethod
    def ask(self, system: str, prompt: str) -> str:
        """Send a system + user prompt and return the model's text reply."""
