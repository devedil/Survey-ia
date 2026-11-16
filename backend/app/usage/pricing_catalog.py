import json
from dataclasses import dataclass

from backend.app.core.config import get_settings


@dataclass(frozen=True)
class ModelPrice:
    version: str
    input_usd_per_million: float
    output_usd_per_million: float


def load_pricing_catalog() -> dict[str, ModelPrice]:
    raw_catalog = get_settings().openai_pricing_catalog
    try:
        catalog = json.loads(raw_catalog)
    except json.JSONDecodeError as error:
        raise ValueError("OPENAI_PRICING_CATALOG must be valid JSON") from error
    if not isinstance(catalog, dict):
        raise ValueError("OPENAI_PRICING_CATALOG must be a JSON object")

    prices = {}
    for model, details in catalog.items():
        if not isinstance(model, str) or not model or not isinstance(details, dict):
            raise ValueError("Each pricing catalog entry must map a model name to a price object")
        version = details.get("version")
        input_price = details.get("input_usd_per_million")
        output_price = details.get("output_usd_per_million")
        if (
            not isinstance(version, str)
            or not version
            or not isinstance(input_price, (float, int))
            or not isinstance(output_price, (float, int))
            or input_price < 0
            or output_price < 0
        ):
            raise ValueError(f"Invalid pricing entry for model {model}")
        prices[model] = ModelPrice(version, float(input_price), float(output_price))
    return prices


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> tuple[float, str] | None:
    price = load_pricing_catalog().get(model)
    if price is None:
        return None
    cost = (
        input_tokens * price.input_usd_per_million
        + output_tokens * price.output_usd_per_million
    ) / 1_000_000
    return cost, price.version
