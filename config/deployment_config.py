"""
Deployment profile and feature flag configuration.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Dict


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default


@dataclass(frozen=True)
class DeploymentConfig:
    profile: str
    erp_enabled: bool
    telegram_enabled: bool
    wake_word_enabled: bool
    voice_mode_default: str
    api_token_required: bool

    def to_public_dict(self) -> Dict[str, object]:
        return asdict(self)


_DEFAULTS = {
    "dev": {
        "erp_enabled": True,
        "telegram_enabled": True,
        "wake_word_enabled": False,
        "voice_mode_default": "agent",
        "api_token_required": False,
    },
    "web": {
        "erp_enabled": True,
        "telegram_enabled": True,
        "wake_word_enabled": False,
        "voice_mode_default": "agent",
        "api_token_required": False,
    },
    "rpi-home": {
        "erp_enabled": False,
        "telegram_enabled": True,
        "wake_word_enabled": True,
        "voice_mode_default": "agent",
        "api_token_required": True,
    },
}

_deployment_config: DeploymentConfig | None = None


def reset_deployment_config_cache() -> None:
    global _deployment_config
    _deployment_config = None


def get_deployment_config() -> DeploymentConfig:
    global _deployment_config
    if _deployment_config is not None:
        return _deployment_config

    profile = _env_str("DEPLOYMENT_PROFILE", "dev")
    defaults = _DEFAULTS.get(profile, _DEFAULTS["dev"])
    voice_mode_default = _env_str(
        "VOICE_MODE_DEFAULT",
        defaults["voice_mode_default"],
    ).lower()
    if voice_mode_default not in {"agent", "live"}:
        voice_mode_default = defaults["voice_mode_default"]

    _deployment_config = DeploymentConfig(
        profile=profile,
        erp_enabled=_env_bool("ERP_ENABLED", defaults["erp_enabled"]),
        telegram_enabled=_env_bool("TELEGRAM_ENABLED", defaults["telegram_enabled"]),
        wake_word_enabled=_env_bool("WAKE_WORD_ENABLED", defaults["wake_word_enabled"]),
        voice_mode_default=voice_mode_default,
        api_token_required=_env_bool("API_TOKEN_REQUIRED", defaults["api_token_required"]),
    )
    return _deployment_config


def is_erp_enabled() -> bool:
    return get_deployment_config().erp_enabled


def is_telegram_enabled() -> bool:
    return get_deployment_config().telegram_enabled


def is_wake_word_enabled() -> bool:
    return get_deployment_config().wake_word_enabled


def is_api_token_required() -> bool:
    return get_deployment_config().api_token_required
