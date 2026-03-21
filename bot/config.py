from pathlib import Path
import yaml

from bot.types import Config


def load_config(config_path: str = None) -> Config:
    """Load configuration from YAML file and parse with Pydantic."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "env_config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return Config.model_validate(data)
