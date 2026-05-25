from dataclasses import dataclass, field


@dataclass
class ProviderProfile:
    """
    Declarative description of an LLM provider.

    WHY: Inspired by Hermes Agent's provider system — each provider is described
    once as a dataclass, not scattered across config handling code. Adding a new
    provider is dropping a new ProviderProfile into profiles.py.

    litellm_prefix: the "provider/" portion of the LiteLLM model string.
    Example: "anthropic/" → model string "anthropic/claude-sonnet-4-6"
    """

    name: str
    display_name: str
    litellm_prefix: str
    env_vars: tuple = field(default_factory=tuple)
    base_url: str = ""
    fallback_models: tuple = field(default_factory=tuple)
    default_model: str = ""
    free: bool = False
    eu_sovereign: bool = False
    local: bool = False
    description: str = ""

    def model_string(self, model_name: str) -> str:
        """Build the LiteLLM model string for this provider + model."""
        return f"{self.litellm_prefix}{model_name}"

    def has_key(self, env: dict) -> bool:
        """Return True if all required env vars are present."""
        return all(env.get(k) for k in self.env_vars)
