from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResearchConfig:
    walk_forward_train_size: int = 240
    walk_forward_test_size: int = 120
    min_trades_by_timeframe: dict[str, int] = field(
        default_factory=lambda: {
            "1m": 120,
            "5m": 100,
            "15m": 80,
            "1h": 10,
            "4h": 5,
            "1d": 3,
        }
    )
    volume_filter_multiplier: float = 0.8
    allow_high_volatility_research_mode: bool = True

    def min_trades_for_timeframe(self, timeframe: str) -> int:
        return int(self.min_trades_by_timeframe.get(timeframe, 20))


def load_research_config(path: str | Path = "research_config.yaml") -> ResearchConfig:
    config_path = Path(path)
    if not config_path.exists():
        return ResearchConfig()
    payload = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    return ResearchConfig(
        walk_forward_train_size=int(payload.get("walk_forward_train_size", 240)),
        walk_forward_test_size=int(payload.get("walk_forward_test_size", 120)),
        min_trades_by_timeframe={
            str(key): int(value)
            for key, value in dict(payload.get("min_trades_by_timeframe", {})).items()
        }
        or ResearchConfig().min_trades_by_timeframe,
        volume_filter_multiplier=float(payload.get("volume_filter_multiplier", 0.8)),
        allow_high_volatility_research_mode=bool(
            payload.get("allow_high_volatility_research_mode", True)
        ),
    )


def _parse_simple_yaml(content: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_map_key: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  ") and current_map_key is not None:
            key, value = line.strip().split(":", 1)
            result.setdefault(current_map_key, {})[key.strip()] = _parse_scalar(value.strip())
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            result[key] = {}
            current_map_key = key
        else:
            result[key] = _parse_scalar(value)
            current_map_key = None
    return result


def _parse_scalar(value: str) -> int | float | bool | str:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
