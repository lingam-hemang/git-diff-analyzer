"""Configuration loading from YAML + environment overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


DEFAULT_CONFIG_PATH = Path.home() / ".git-diff-analyzer.yaml"
LOCAL_CONFIG_PATH = Path(".git-diff-analyzer.yaml")


class BedrockConfig(BaseModel):
    region: str = "us-east-1"
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    max_tokens: int = 4096
    temperature: float = 0.1
    profile: Optional[str] = None  # AWS profile name; None = default credential chain


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    timeout: int = 120
    max_tokens: int = 4096
    temperature: float = 0.1


class OutputConfig(BaseModel):
    base_dir: Path = Path("output")
    docs_dir: Path = Path("output/docs")
    dml_dir: Path = Path("output/dml")
    create_dirs: bool = True


class SnowflakeConfig(BaseModel):
    database: str = "MY_DATABASE"
    schema_name: str = "PUBLIC"
    warehouse: str = "COMPUTE_WH"
    role: Optional[str] = None
    use_transactions: bool = True  # wrap scripts in BEGIN / ROLLBACK by default


class AnalysisConfig(BaseModel):
    max_diff_size: int = 50_000  # total chars across all files in one prompt
    max_file_diff_size: int = 8_000  # per-file cap
    default_provider: Literal["bedrock", "ollama"] = "ollama"
    verbose: bool = False


class DeploymentConfig(BaseModel):
    mode: Literal["local", "aws"] = "local"


class AwsLambdaConfig(BaseModel):
    trigger_source: Literal["github", "codecommit", "both"] = "github"
    github_webhook_secret: Optional[str] = None
    codecommit_repo_arn: Optional[str] = None


class S3Config(BaseModel):
    bucket: str = ""
    prefix: str = "git-diff-analyzer/"
    region: Optional[str] = None


class AppConfig(BaseModel):
    bedrock: BedrockConfig = Field(default_factory=BedrockConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    snowflake: SnowflakeConfig = Field(default_factory=SnowflakeConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    aws_lambda: AwsLambdaConfig = Field(default_factory=AwsLambdaConfig)
    s3: S3Config = Field(default_factory=S3Config)

    @field_validator("output", mode="before")
    @classmethod
    def _coerce_output(cls, v: Any) -> Any:
        if isinstance(v, dict):
            # convert string paths to Path objects
            for key in ("base_dir", "docs_dir", "dml_dir"):
                if key in v and isinstance(v[key], str):
                    v[key] = Path(v[key])
        return v

    def ensure_output_dirs(self) -> None:
        if self.output.create_dirs:
            self.output.docs_dir.mkdir(parents=True, exist_ok=True)
            self.output.dml_dir.mkdir(parents=True, exist_ok=True)


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open() as fh:
        data = yaml.safe_load(fh) or {}
    return data  # type: ignore[return-value]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base (override wins)."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """
    Load configuration with the following precedence (highest wins):
      1. CLI-supplied config_path
      2. .git-diff-analyzer.yaml in the current working directory
      3. ~/.git-diff-analyzer.yaml (home directory)
      4. Built-in defaults (AppConfig field defaults)

    Environment variable GDA_CONFIG can also point to a config file.
    """
    merged: Dict[str, Any] = {}

    # Home dir config (lowest file precedence)
    if DEFAULT_CONFIG_PATH.is_file():
        merged = _deep_merge(merged, _load_yaml(DEFAULT_CONFIG_PATH))

    # Local dir config overrides home
    if LOCAL_CONFIG_PATH.is_file():
        merged = _deep_merge(merged, _load_yaml(LOCAL_CONFIG_PATH))

    # Explicit path overrides everything
    env_path = os.environ.get("GDA_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            merged = _deep_merge(merged, _load_yaml(p))

    if config_path and config_path.is_file():
        merged = _deep_merge(merged, _load_yaml(config_path))

    return AppConfig.model_validate(merged)


def write_example_config(dest: Path) -> None:
    """Copy config.example.yaml to dest."""
    example = Path(__file__).parent.parent.parent / "config.example.yaml"
    if example.is_file():
        dest.write_text(example.read_text())
    else:
        # Fallback: write defaults as YAML
        cfg = AppConfig()
        data = cfg.model_dump(mode="json")
        dest.write_text(yaml.dump(data, default_flow_style=False))
