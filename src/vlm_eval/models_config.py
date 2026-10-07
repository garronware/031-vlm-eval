"""Reads config/models.yaml: the makers and models tested, their prices and thinking levels."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from vlm_eval import paths

MAKER_DEFAULT = "maker default"


@dataclass(frozen=True)
class Model:
    maker: str  # anthropic | openai | google | xai
    id: str  # the maker's API name, e.g. claude-opus-5
    name: str  # for people, e.g. Claude Opus 5
    role: str  # default | top | other | extractor
    enabled: bool  # the model and its maker are both switched on
    key: str  # the .env variable holding the maker's API key
    thinking: str  # "maker default", or one of `levels`
    maker_default: str  # what the maker does when nothing is sent
    levels: tuple[str, ...]
    input_price: Decimal  # US dollars per million tokens
    output_price: Decimal  # thinking tokens are billed as output


def load_models(path: Path = paths.MODELS_YAML) -> list[Model]:
    config = yaml.safe_load(path.read_text())
    models = []
    for maker, entry in config["makers"].items():
        for m in entry["models"]:
            price = m["price_per_million_tokens"]
            models.append(
                Model(
                    maker=maker,
                    id=m["id"],
                    name=m["name"],
                    role=m["role"],
                    enabled=bool(entry["enabled"] and m["enabled"]),
                    key=entry["key"],
                    thinking=m["thinking"],
                    maker_default=m["maker_default"],
                    levels=tuple(m["levels"]),
                    input_price=Decimal(str(price["input"])),
                    output_price=Decimal(str(price["output"])),
                )
            )
    return models


def enabled_models(path: Path = paths.MODELS_YAML) -> list[Model]:
    return [m for m in load_models(path) if m.enabled]


def load_extractor(path: Path = paths.MODELS_YAML) -> Model:
    """The model that copies replies into the answer form. Never a tested model."""
    entry = yaml.safe_load(path.read_text())["extractor"]
    price = entry["price_per_million_tokens"]
    return Model(
        maker=entry["maker"],
        id=entry["id"],
        name=entry["name"],
        role="extractor",
        enabled=False,  # never part of a test run
        key=entry["key"],
        thinking=MAKER_DEFAULT,
        maker_default="no thinking",
        levels=(),
        input_price=Decimal(str(price["input"])),
        output_price=Decimal(str(price["output"])),
    )
