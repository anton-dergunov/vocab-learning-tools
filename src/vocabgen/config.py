from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple, Union

import yaml
from box import Box


ConfigPath = Union[str, Path]


def load_yaml(path: ConfigPath) -> dict[str, Any]:
    """Load a YAML file and require a mapping at its root."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping: {config_path}")
    return data


def deep_merge(
    base: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a recursive merge without modifying either input mapping."""
    merged = deepcopy(dict(base))
    for key, override_value in overrides.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(override_value, Mapping):
            merged[key] = deep_merge(base_value, override_value)
        else:
            merged[key] = deepcopy(override_value)
    return merged


def load_config(
    defaults_path: ConfigPath,
    override_path: Optional[ConfigPath] = None,
) -> Box:
    """Load tracked defaults and optionally merge a local YAML overlay."""
    config = load_yaml(defaults_path)
    if override_path is not None:
        config = deep_merge(config, load_yaml(override_path))
    return Box(config)


def select_llm_provider(
    config: Box,
    requested_provider: Optional[str] = None,
) -> Tuple[str, dict[str, Any]]:
    """Resolve an LLM provider and its factory configuration."""
    provider_name = requested_provider or config.llm.default_provider
    providers = config.llm.providers

    if provider_name not in providers:
        available = ", ".join(sorted(providers.keys()))
        raise ValueError(
            f"Unknown LLM provider {provider_name!r}. Configured providers: {available}"
        )

    provider = providers[provider_name]
    options = provider.get("options", Box()).to_dict()
    provider_config = {"provider": provider_name, "options": options}
    return provider_name, provider_config
