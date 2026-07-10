from __future__ import annotations

import json
import ast
from pathlib import Path
from typing import Any


ALLOWED_COMMANDS = {
    "--version",
    "download-data",
    "list-data",
    "list-strategies",
    "backtesting",
    "backtesting-analysis",
    "lookahead-analysis",
    "recursive-analysis",
}
FORBIDDEN_TOKENS = {"live", "real", "production", "futures", "margin", "leverage", "short", "freqai", "remote-pairlist", "producer", "consumer", "webhook"}
SECRET_FIELDS = {"key", "secret", "password", "api_key", "api_secret"}
SAFE_STRATEGIES = {"EmaCrossoverStrategy", "RsiMeanReversionStrategy", "BreakoutStrategy"}
STRATEGY_DIRECTORY = Path("freqtrade_user_data/strategies")


class FreqtradeSafetyError(ValueError):
    """Raised before any unsafe or unsupported Freqtrade invocation."""


def load_paper_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_file():
        raise FreqtradeSafetyError(f"Freqtrade config not found: {config_path}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FreqtradeSafetyError("Freqtrade config is not valid JSON") from exc
    validate_paper_config(config)
    return config


def validate_paper_config(config: dict[str, Any]) -> None:
    if config.get("dry_run") is not True:
        raise FreqtradeSafetyError("Freqtrade requires dry_run=true")
    if config.get("trading_mode") != "spot":
        raise FreqtradeSafetyError("Freqtrade requires trading_mode=spot")
    if "margin_mode" in config or "leverage" in config:
        raise FreqtradeSafetyError("margin and leverage are forbidden")
    if bool(config.get("can_short")):
        raise FreqtradeSafetyError("short selling is forbidden")
    exchange = config.get("exchange")
    if not isinstance(exchange, dict):
        raise FreqtradeSafetyError("Freqtrade exchange config is required")
    for field in ("key", "secret", "password"):
        if str(exchange.get(field, "")):
            raise FreqtradeSafetyError(f"Freqtrade exchange {field} must be empty")
    if bool(config.get("freqai", {}).get("enabled")):
        raise FreqtradeSafetyError("FreqAI is forbidden")
    pairlists = config.get("pairlists", [])
    if any("remote" in str(item).lower() for item in pairlists):
        raise FreqtradeSafetyError("remote pairlists are forbidden")
    blacklist = " ".join(str(item) for item in exchange.get("pair_blacklist", []))
    if not all(token in blacklist.upper() for token in ("UP", "DOWN", "BULL", "BEAR", "PERP", "FUTURES", "SWAP")):
        raise FreqtradeSafetyError("paper config must blacklist leveraged and derivative pairs")
    _reject_nonempty_secrets(config)


def validate_command(command: str, arguments: list[str], config: dict[str, Any], candidate: dict[str, Any] | None = None) -> None:
    if command not in ALLOWED_COMMANDS:
        raise FreqtradeSafetyError(f"Freqtrade command is not allowlisted: {command}")
    joined = " ".join([command, *arguments]).lower()
    if any(token in joined for token in FORBIDDEN_TOKENS):
        raise FreqtradeSafetyError("unsafe Freqtrade command argument detected")
    validate_paper_config(config)
    _validate_strategy_argument(arguments)


def _validate_strategy_argument(arguments: list[str]) -> None:
    if "--strategy" not in arguments:
        return
    index = arguments.index("--strategy")
    if index == len(arguments) - 1:
        raise FreqtradeSafetyError("--strategy requires a strategy name")
    strategy_name = arguments[index + 1]
    if strategy_name not in SAFE_STRATEGIES:
        raise FreqtradeSafetyError(f"strategy is not allowlisted: {strategy_name}")
    strategy_path = STRATEGY_DIRECTORY / f"{strategy_name}.py"
    tree = ast.parse(strategy_path.read_text(encoding="utf-8"), filename=str(strategy_path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "can_short" for target in targets):
                value = node.value
                if isinstance(value, ast.Constant) and value.value is True:
                    raise FreqtradeSafetyError(f"strategy enables short selling: {strategy_name}")


def _reject_nonempty_secrets(value: Any, field_name: str | None = None) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _reject_nonempty_secrets(nested, str(key).lower())
    elif isinstance(value, list):
        for nested in value:
            _reject_nonempty_secrets(nested, field_name)
    elif field_name in SECRET_FIELDS and str(value):
        raise FreqtradeSafetyError(f"non-empty secret field is forbidden: {field_name}")
