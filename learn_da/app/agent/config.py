from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config.settings import settings


@dataclass
class ModelConfig:
    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.3
    max_tokens: Optional[int] = None
    priority: int = 0


@dataclass
class AgentConfig:
    models: List[ModelConfig] = field(default_factory=list)
    default_model: Optional[str] = None
    fallback_enabled: bool = True
    max_history_turns: int = 6
    enable_streaming: bool = True


def load_agent_config() -> AgentConfig:
    config = AgentConfig()

    primary_api_key = settings.effective_llm_api_key
    primary_base_url = settings.effective_llm_base_url
    primary_model = settings.effective_llm_model

    if primary_api_key and primary_base_url:
        config.models.append(
            ModelConfig(
                name=primary_model,
                api_key=primary_api_key,
                base_url=primary_base_url,
                priority=100,
            )
        )
        config.default_model = primary_model

    config.fallback_enabled = True
    config.max_history_turns = getattr(settings, "OPENAI_MAX_TURNS", 3) * 2
    config.enable_streaming = True

    return config


def get_model_config(config: AgentConfig, model_name: Optional[str] = None) -> Optional[ModelConfig]:
    if not config.models:
        return None

    target_name = model_name or config.default_model
    if not target_name:
        sorted_models = sorted(config.models, key=lambda m: m.priority, reverse=True)
        return sorted_models[0] if sorted_models else None

    for model in config.models:
        if model.name == target_name:
            return model

    return None
