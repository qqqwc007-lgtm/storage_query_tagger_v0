from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .normalizer import normalize_text
from .taxonomy_registry import ALL_FIELDS


SAFE_AUTO_PATCH_TYPES = {"taxonomy_alias", "candidate_suppression"}


@dataclass
class PatchApplyResult:
    applied: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    backup_dir: str = ""
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied_count": len(self.applied),
            "skipped_count": len(self.skipped),
            "changed_files": self.changed_files,
            "backup_dir": self.backup_dir,
            "dry_run": self.dry_run,
            "applied": self.applied,
            "skipped": self.skipped,
        }


def copy_config_tree(source_config_root: str | Path, target_config_root: str | Path, overwrite: bool = False) -> None:
    source = Path(source_config_root)
    target = Path(target_config_root)
    if not source.exists():
        raise FileNotFoundError(f"Config root does not exist: {source}")
    if target.exists():
        if not overwrite:
            return
        shutil.rmtree(target)
    shutil.copytree(source, target)


def taxonomy_fingerprint(config_root: str | Path) -> str:
    root = Path(config_root)
    hasher = hashlib.sha256()
    for path in sorted((root / "taxonomy").glob("*.json")) + sorted((root / "rules").glob("*.yaml")):
        hasher.update(str(path.relative_to(root)).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def apply_taxonomy_patch_proposals(
    config_root: str | Path,
    proposals_jsonl: str | Path,
    output_dir: str | Path | None = None,
    apply: bool = False,
    auto_apply_only: bool = True,
    backup: bool = True,
) -> PatchApplyResult:
    config_root = Path(config_root)
    output_dir = Path(output_dir) if output_dir else config_root
    proposals_path = Path(proposals_jsonl)
    result = PatchApplyResult(dry_run=not apply)

    proposals = _read_jsonl(proposals_path)
    taxonomy_dir = config_root / "taxonomy"
    canonical_path = taxonomy_dir / "canonical_values_v0.json"
    aliases_path = taxonomy_dir / "aliases_v0.json"
    suppression_path = taxonomy_dir / "candidate_suppression_v0.json"

    canonical_values = _read_json(canonical_path)
    aliases = _read_json(aliases_path)
    suppression = _read_json(suppression_path) if suppression_path.exists() else {"suppressed_terms": []}

    canonical_keys = {
        (str(record.get("axis", "")), str(record.get("canonical_value", "")))
        for record in canonical_values
    }
    alias_keys = {
        (
            str(record.get("axis", "")),
            str(record.get("canonical_value", "")),
            normalize_text(record.get("alias", "")),
        )
        for record in aliases
    }
    suppressed_terms = {
        normalize_text(term)
        for term in suppression.get("suppressed_terms", [])
        if normalize_text(term)
    }

    changed_aliases = False
    changed_suppression = False

    for proposal in proposals:
        patch_type = str(proposal.get("patch_type", ""))
        auto_apply_eligible = bool(proposal.get("auto_apply_eligible"))
        if auto_apply_only and (not auto_apply_eligible or patch_type not in SAFE_AUTO_PATCH_TYPES):
            result.skipped.append(_skip(proposal, "not_auto_apply_eligible"))
            continue

        if patch_type == "taxonomy_alias":
            applied, reason = _apply_alias_proposal(
                proposal=proposal,
                aliases=aliases,
                alias_keys=alias_keys,
                canonical_keys=canonical_keys,
            )
            if applied:
                changed_aliases = True
                result.applied.append({"patch_type": patch_type, "reason": reason, "proposal": proposal})
            else:
                result.skipped.append(_skip(proposal, reason))
            continue

        if patch_type == "candidate_suppression":
            applied_terms = _apply_suppression_proposal(proposal, suppressed_terms)
            if applied_terms:
                suppression["suppressed_terms"] = sorted(suppressed_terms)
                changed_suppression = True
                result.applied.append({
                    "patch_type": patch_type,
                    "terms": applied_terms,
                    "proposal": proposal,
                })
            else:
                result.skipped.append(_skip(proposal, "duplicate_or_empty_suppression"))
            continue

        result.skipped.append(_skip(proposal, f"unsupported_or_unsafe_patch_type:{patch_type}"))

    if apply and result.applied:
        if backup:
            result.backup_dir = _backup_taxonomy_files(taxonomy_dir, output_dir)
        if changed_aliases:
            _write_json_atomic(aliases_path, aliases)
            result.changed_files.append(str(aliases_path))
        if changed_suppression:
            _write_json_atomic(suppression_path, suppression)
            result.changed_files.append(str(suppression_path))

    return result


def write_patch_summary(summary_path: str | Path, result: PatchApplyResult) -> None:
    Path(summary_path).write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _apply_alias_proposal(
    proposal: dict[str, Any],
    aliases: list[dict[str, Any]],
    alias_keys: set[tuple[str, str, str]],
    canonical_keys: set[tuple[str, str]],
) -> tuple[bool, str]:
    record = proposal.get("record", {})
    axis = str(record.get("axis") or "").strip()
    canonical_value = str(record.get("canonical_value") or "").strip()
    raw_aliases = record.get("aliases", [])
    if axis not in ALL_FIELDS:
        return False, "invalid_axis"
    if (axis, canonical_value) not in canonical_keys:
        return False, "unknown_canonical_value"
    if not isinstance(raw_aliases, list):
        raw_aliases = [raw_aliases]

    added = False
    for alias in raw_aliases:
        clean_alias = normalize_text(alias)
        if not clean_alias:
            continue
        key = (axis, canonical_value, clean_alias)
        if key in alias_keys:
            continue
        aliases.append({
            "axis": axis,
            "canonical_value": canonical_value,
            "alias": clean_alias,
        })
        alias_keys.add(key)
        added = True
    return added, "applied_alias" if added else "duplicate_or_empty_alias"


def _apply_suppression_proposal(proposal: dict[str, Any], suppressed_terms: set[str]) -> list[str]:
    record = proposal.get("record", {})
    raw_terms = record.get("terms", [])
    if not isinstance(raw_terms, list):
        raw_terms = [raw_terms]

    applied_terms = []
    for term in raw_terms:
        clean_term = normalize_text(term)
        if not clean_term or clean_term in suppressed_terms:
            continue
        suppressed_terms.add(clean_term)
        applied_terms.append(clean_term)
    return applied_terms


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: Path, data: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _backup_taxonomy_files(taxonomy_dir: Path, output_dir: Path) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = output_dir / "taxonomy_patch_backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in taxonomy_dir.glob("*.json"):
        shutil.copy2(path, backup_dir / path.name)
    return str(backup_dir)


def _skip(proposal: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "proposal": proposal,
    }
