"""Configuration management module."""

import json
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class RepoConfig:
    """Configuration for a single repository."""
    owner: str
    name: str
    level: str = "all"  # all / merged_and_release / release_only
    frequency: str = "1d"  # 1d / 2d / on_release
    keywords: list[str] = field(default_factory=list)
    enable_tg: bool = False

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass
class AIConfig:
    """AI provider configuration."""
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""
    bot_token: str
    chat_id: str
    enabled: bool = False


@dataclass
class ProxyConfig:
    """HTTP proxy configuration."""
    enabled: bool = False
    http_proxy: str = ""
    https_proxy: str = ""

    @property
    def proxies(self) -> Optional[dict]:
        """Return proxies dict for requests library."""
        if not self.enabled:
            return None
        result = {}
        if self.http_proxy:
            result["http"] = self.http_proxy
        if self.https_proxy:
            result["https"] = self.https_proxy
        return result if result else None

    @property
    def proxy_url(self) -> Optional[str]:
        """Return single proxy URL (prefer https)."""
        if not self.enabled:
            return None
        return self.https_proxy or self.http_proxy or None


@dataclass
class Config:
    """Main configuration class."""
    github_token: Optional[str]
    ai: AIConfig
    telegram: TelegramConfig
    proxy: ProxyConfig
    repos: list[RepoConfig]
    data_dir: str = "./data"
    reports_dir: str = "./data/reports"

    @classmethod
    def load(cls, config_path: str = "config.json") -> "Config":
        """Load configuration from JSON file."""
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Parse AI config
        ai_data = data.get("ai", {})
        ai_config = AIConfig(
            api_key=ai_data.get("api_key", os.getenv("AI_API_KEY", "")),
            base_url=ai_data.get("base_url", "https://api.openai.com/v1"),
            model=ai_data.get("model", "gpt-4o-mini")
        )

        # Parse Telegram config
        tg_data = data.get("telegram", {})
        telegram_config = TelegramConfig(
            bot_token=tg_data.get("bot_token", os.getenv("TG_BOT_TOKEN", "")),
            chat_id=tg_data.get("chat_id", os.getenv("TG_CHAT_ID", "")),
            enabled=tg_data.get("enabled", False)
        )

        # Parse Proxy config
        proxy_data = data.get("proxy", {})
        proxy_config = ProxyConfig(
            enabled=proxy_data.get("enabled", False),
            http_proxy=proxy_data.get("http_proxy", os.getenv("HTTP_PROXY", "")),
            https_proxy=proxy_data.get("https_proxy", os.getenv("HTTPS_PROXY", ""))
        )

        # Parse repos config
        repos = []
        for repo_data in data.get("repos", []):
            repos.append(RepoConfig(
                owner=repo_data["owner"],
                name=repo_data["name"],
                level=repo_data.get("level", "all"),
                frequency=repo_data.get("frequency", "1d"),
                keywords=repo_data.get("keywords", []),
                enable_tg=repo_data.get("enable_tg", False)
            ))

        return cls(
            github_token=data.get("github_token") or os.getenv("GITHUB_TOKEN"),
            ai=ai_config,
            telegram=telegram_config,
            proxy=proxy_config,
            repos=repos,
            data_dir=data.get("data_dir", "./data"),
            reports_dir=data.get("reports_dir", "./data/reports")
        )

    def get_repo_by_name(self, full_name: str) -> Optional[RepoConfig]:
        """Get repository configuration by full name."""
        for repo in self.repos:
            if repo.full_name == full_name:
                return repo
        return None
