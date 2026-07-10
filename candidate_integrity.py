from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class CandidateIntegrityError(ValueError):
    pass


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_candidate(candidate_path: str | Path, strategy_path: str | Path, config_path: str | Path) -> dict[str, Any]:
    candidate = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
    if candidate.get("allowed_next_mode") not in {"report_only", "freqtrade_dry_run"}:
        raise CandidateIntegrityError("invalid candidate allowed_next_mode")
    if candidate.get("strategy_hash") != sha256_file(strategy_path):
        raise CandidateIntegrityError("strategy hash changed; a new benchmark is required")
    if candidate.get("config_hash") != sha256_file(config_path):
        raise CandidateIntegrityError("config hash changed; a new benchmark is required")
    return candidate
