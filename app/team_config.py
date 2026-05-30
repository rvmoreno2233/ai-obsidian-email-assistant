"""Shared team configuration for multi-user deployments."""

from __future__ import annotations

import yaml
from pydantic import BaseModel, Field

from app.config import DATA_DIR, PROJECT_ROOT

TEAM_CONFIG_DIR = PROJECT_ROOT / "config"
TEAM_CONFIG_FILE = TEAM_CONFIG_DIR / "team.yaml"
TEAM_CONFIG_EXAMPLE = TEAM_CONFIG_DIR / "team.yaml.example"


class ScrapeDefaults(BaseModel):
    max_pages: int = 100
    page_size: int = 100


class AgentDefaults(BaseModel):
    max_agents: int = 25
    min_messages_for_company: int = 3


class TeamConfig(BaseModel):
    team_name: str = "Email Assistant Team"
    organization: str = ""
    tenant_id: str = ""
    vault_path: str = "vault"
    data_dir: str = "data"
    scrape_defaults: ScrapeDefaults = Field(default_factory=ScrapeDefaults)
    agent_defaults: AgentDefaults = Field(default_factory=AgentDefaults)
    categories: dict[str, str] = Field(default_factory=dict)
    domain_hints: dict[str, str] = Field(default_factory=dict)


def load_team_config() -> TeamConfig:
    path = TEAM_CONFIG_FILE if TEAM_CONFIG_FILE.exists() else TEAM_CONFIG_EXAMPLE
    if not path.exists():
        return TeamConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TeamConfig.model_validate(data)


def save_team_config(config: TeamConfig) -> None:
    TEAM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TEAM_CONFIG_FILE.write_text(
        yaml.dump(
            config.model_dump(),
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def sync_hints_to_domain_categories(config: TeamConfig) -> None:
    """Merge team domain_hints into data/domain_categories.yaml."""
    path = DATA_DIR / "domain_categories.yaml"
    existing: dict = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    existing["categories"] = config.categories or existing.get("categories", {})
    existing["hints"] = {**existing.get("hints", {}), **config.domain_hints}
    path.write_text(
        yaml.dump(existing, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
