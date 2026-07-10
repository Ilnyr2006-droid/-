from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class HoldoutIsolationError(ValueError):
    pass


def freeze_config(config: dict[str, Any], output: str | Path) -> str:
    serialized = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    Path(output).write_text(json.dumps({"config": config, "sha256": digest}, indent=2), encoding="utf-8")
    return digest


def validate_stage_command(stage: str, command: str, config_hash: str | None = None) -> None:
    if stage not in {"development", "validation", "holdout"}:
        raise HoldoutIsolationError("unknown split stage")
    if stage in {"validation", "holdout"} and command.startswith("hyperopt"):
        raise HoldoutIsolationError("hyperopt is forbidden outside development")
    if stage == "holdout" and not config_hash:
        raise HoldoutIsolationError("holdout requires a frozen configuration hash")
