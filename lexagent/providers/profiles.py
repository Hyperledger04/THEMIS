"""
Built-in provider profiles — 15 providers ready out of the box.

WHY: Every provider here works with LiteLLM as the transport layer, which is
already installed. No new SDKs needed — LiteLLM handles the HTTP translation.

Ordering: most common first (Anthropic, OpenAI, Google), then specialist
(Groq fast/free, Mistral EU), then local (Ollama, LMStudio), then meta-routers.
"""

from lexagent.providers.base import ProviderProfile

PROVIDERS: list[ProviderProfile] = [
    ProviderProfile(
        name="anthropic",
        display_name="Anthropic Claude",
        litellm_prefix="anthropic/",
        env_vars=("ANTHROPIC_API_KEY",),
        fallback_models=("claude-haiku-4-5-20251001", "claude-sonnet-4-6"),
        default_model="claude-sonnet-4-6",
        inference_tier=4,
        description="Best for legal drafting. Supports extended thinking and prompt caching.",
    ),
    ProviderProfile(
        name="openai",
        display_name="OpenAI / GPT-4",
        litellm_prefix="openai/",
        env_vars=("OPENAI_API_KEY",),
        fallback_models=("gpt-4o-mini", "gpt-4o"),
        default_model="gpt-4o",
        inference_tier=4,
        description="Strong reasoning. Good for complex analysis.",
    ),
    ProviderProfile(
        name="gemini",
        display_name="Google Gemini",
        litellm_prefix="gemini/",
        env_vars=("GOOGLE_API_KEY",),
        fallback_models=("gemini-1.5-flash", "gemini-1.5-pro"),
        default_model="gemini-1.5-pro",
        inference_tier=4,
        description="Long context window. Good for large document review.",
    ),
    ProviderProfile(
        name="groq",
        display_name="Groq (fast, free tier)",
        litellm_prefix="groq/",
        env_vars=("GROQ_API_KEY",),
        fallback_models=("llama-3.1-8b-instant", "llama-3.3-70b-versatile"),
        default_model="llama-3.3-70b-versatile",
        free=True,
        inference_tier=5,
        description="Fastest inference available. Free tier. Great for intake questions.",
    ),
    ProviderProfile(
        name="deepseek",
        display_name="DeepSeek",
        litellm_prefix="deepseek/",
        env_vars=("DEEPSEEK_API_KEY",),
        fallback_models=("deepseek-chat",),
        default_model="deepseek-chat",
        inference_tier=4,
        description="Cheap and strong. Excellent value for high-volume drafting.",
    ),
    ProviderProfile(
        name="mistral",
        display_name="Mistral AI (EU sovereign)",
        litellm_prefix="mistral/",
        env_vars=("MISTRAL_API_KEY",),
        fallback_models=("mistral-small-latest", "mistral-large-latest"),
        default_model="mistral-large-latest",
        eu_sovereign=True,
        inference_tier=4,
        description="EU data residency. Required for GDPR-strict European law firms.",
    ),
    ProviderProfile(
        name="xai",
        display_name="xAI Grok",
        litellm_prefix="xai/",
        env_vars=("XAI_API_KEY",),
        fallback_models=("grok-beta",),
        default_model="grok-beta",
        inference_tier=4,
        description="Strong reasoning model with real-time web access.",
    ),
    ProviderProfile(
        name="openrouter",
        display_name="OpenRouter (any model)",
        litellm_prefix="openrouter/",
        env_vars=("OPENROUTER_API_KEY",),
        fallback_models=("meta-llama/llama-3.1-8b-instruct:free",),
        default_model="anthropic/claude-sonnet-4-6",
        inference_tier=4,
        description="Routes to 200+ models. One key for everything.",
    ),
    ProviderProfile(
        name="ollama",
        display_name="Ollama (local, fully private)",
        litellm_prefix="ollama/",
        env_vars=(),
        base_url="http://localhost:11434",
        fallback_models=("llama3.2:3b", "gemma3:4b"),
        default_model="llama3.2",
        free=True,
        local=True,
        inference_tier=1,
        description="Runs on your machine. Zero API calls. Full privacy for client data.",
    ),
    ProviderProfile(
        name="lmstudio",
        display_name="LM Studio (local)",
        litellm_prefix="openai/",
        env_vars=(),
        base_url="http://localhost:1234/v1",
        fallback_models=(),
        default_model="local-model",
        free=True,
        local=True,
        inference_tier=1,
        description="Local models via LM Studio GUI. Uses OpenAI-compat API.",
    ),
    ProviderProfile(
        name="together",
        display_name="Together AI",
        litellm_prefix="together_ai/",
        env_vars=("TOGETHER_API_KEY",),
        fallback_models=("meta-llama/Llama-3-8b-chat-hf",),
        default_model="meta-llama/Llama-3-70b-chat-hf",
        inference_tier=4,
        description="Open-source models at competitive prices.",
    ),
    ProviderProfile(
        name="azure",
        display_name="Azure OpenAI",
        litellm_prefix="azure/",
        env_vars=("AZURE_API_KEY", "AZURE_API_BASE"),
        fallback_models=(),
        default_model="gpt-4o",
        inference_tier=3,
        description="Azure-hosted OpenAI. Required for Azure enterprise agreements.",
    ),
    ProviderProfile(
        name="bedrock",
        display_name="AWS Bedrock",
        litellm_prefix="bedrock/",
        env_vars=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
        fallback_models=("anthropic.claude-3-sonnet-20240229-v1:0",),
        default_model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        inference_tier=3,
        description="AWS-hosted models. For firms with AWS enterprise agreements.",
    ),
    ProviderProfile(
        name="nvidia",
        display_name="NVIDIA NIM",
        litellm_prefix="nvidia_nim/",
        env_vars=("NVIDIA_NIM_API_KEY",),
        fallback_models=("meta/llama-3.1-8b-instruct",),
        default_model="meta/llama-3.1-70b-instruct",
        inference_tier=3,
        description="GPU-accelerated inference via NVIDIA cloud.",
    ),
    ProviderProfile(
        name="custom",
        display_name="Custom / Self-hosted",
        litellm_prefix="openai/",
        env_vars=(),
        base_url="",
        fallback_models=(),
        default_model="custom-model",
        inference_tier=2,
        description="Any OpenAI-compatible endpoint. Enter the base URL manually.",
    ),
]

# Build lookup dict once at module load
_REGISTRY: dict[str, ProviderProfile] = {p.name: p for p in PROVIDERS}


def get_profile(name: str) -> ProviderProfile | None:
    return _REGISTRY.get(name)


def list_profiles() -> list[ProviderProfile]:
    return list(PROVIDERS)
