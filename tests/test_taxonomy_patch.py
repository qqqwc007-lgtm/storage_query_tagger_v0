import json
from pathlib import Path

from storage_taxonomy.taxonomy_patch import (
    apply_taxonomy_patch_proposals,
    copy_config_tree,
    taxonomy_fingerprint,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_apply_taxonomy_patch_proposals_alias_and_suppression(tmp_path):
    source = Path("config")
    config_root = tmp_path / "config"
    copy_config_tree(source, config_root, overwrite=True)

    proposals_path = tmp_path / "patches.jsonl"
    _write_jsonl(proposals_path, [
        {
            "patch_type": "taxonomy_alias",
            "auto_apply_eligible": True,
            "record": {
                "axis": "产品形态关键词",
                "canonical_value": "box",
                "aliases": ["storage crate"],
            },
            "source": {},
        },
        {
            "patch_type": "candidate_suppression",
            "auto_apply_eligible": True,
            "record": {
                "terms": ["adjustable"],
                "reason": "generic modifier",
            },
            "source": {},
        },
    ])

    before = taxonomy_fingerprint(config_root)
    result = apply_taxonomy_patch_proposals(
        config_root=config_root,
        proposals_jsonl=proposals_path,
        output_dir=tmp_path,
        apply=True,
        auto_apply_only=True,
    )
    after = taxonomy_fingerprint(config_root)

    assert len(result.applied) == 2
    assert before != after

    aliases = json.loads((config_root / "taxonomy" / "aliases_v0.json").read_text(encoding="utf-8"))
    assert any(row["canonical_value"] == "box" and row["alias"] == "storage crate" for row in aliases)

    suppression = json.loads((config_root / "taxonomy" / "candidate_suppression_v0.json").read_text(encoding="utf-8"))
    assert "adjustable" in suppression["suppressed_terms"]


def test_apply_taxonomy_patch_proposals_skips_unsafe_patch(tmp_path):
    config_root = tmp_path / "config"
    copy_config_tree("config", config_root, overwrite=True)
    proposals_path = tmp_path / "patches.jsonl"
    _write_jsonl(proposals_path, [
        {
            "patch_type": "taxonomy_canonical_value",
            "auto_apply_eligible": False,
            "record": {
                "axis": "产品形态关键词",
                "canonical_value": "crate",
            },
            "source": {},
        }
    ])

    result = apply_taxonomy_patch_proposals(
        config_root=config_root,
        proposals_jsonl=proposals_path,
        output_dir=tmp_path,
        apply=True,
        auto_apply_only=True,
    )

    assert not result.applied
    assert result.skipped
