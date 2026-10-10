"""Guide persistence under runtime_dir/guides (one JSON, optional XML per slug)."""

from __future__ import annotations

import json
from pathlib import Path
import re

from companion.builds.guide import BreakerRule, GuideProfile
from companion.state.store import atomic_write_file

_ASSIGNMENTS = "_assignments.json"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-")
    if not slug:
        raise ValueError("Nama guide tidak valid")
    return slug


def _dir(runtime_dir: Path) -> Path:
    return Path(runtime_dir) / "guides"


def _json(runtime_dir: Path, slug: str) -> Path:
    return _dir(runtime_dir) / f"{slugify(slug)}.json"


def _xml(runtime_dir: Path, slug: str) -> Path:
    return _dir(runtime_dir) / f"{slugify(slug)}.xml"


def load_guide(runtime_dir: Path, slug: str) -> GuideProfile | None:
    try:
        path = _json(runtime_dir, slug)
    except ValueError:
        return None
    if not path.exists():
        return None
    return GuideProfile.model_validate_json(path.read_text(encoding="utf-8"))


def load_guide_xml(runtime_dir: Path, slug: str) -> str | None:
    try:
        path = _xml(runtime_dir, slug)
    except ValueError:
        return None
    return path.read_text(encoding="utf-8") if path.exists() else None


def _write(runtime_dir: Path, profile: GuideProfile) -> None:
    atomic_write_file(
        _json(runtime_dir, profile.slug),
        profile.model_dump_json(indent=2).encode("utf-8"),
    )


def save_guide(runtime_dir: Path, profile: GuideProfile, pob_xml: str | None = None) -> GuideProfile:
    profile = profile.model_copy(update={"slug": slugify(profile.slug)})
    existing = load_guide(runtime_dir, profile.slug)
    if existing is not None:
        profile = profile.model_copy(update={"breaker_rules": existing.breaker_rules})
    _write(runtime_dir, profile)
    if pob_xml is not None:
        atomic_write_file(_xml(runtime_dir, profile.slug), pob_xml.encode("utf-8"))
    elif not profile.has_pob:
        _xml(runtime_dir, profile.slug).unlink(missing_ok=True)  # drop a stale XML from an earlier import
    return profile


def list_guides(runtime_dir: Path) -> list[GuideProfile]:
    d = _dir(runtime_dir)
    if not d.exists():
        return []
    guides = [
        GuideProfile.model_validate_json(p.read_text(encoding="utf-8"))
        for p in d.glob("*.json")
        if p.name != _ASSIGNMENTS
    ]
    return sorted(guides, key=lambda g: g.name)


def delete_guide(runtime_dir: Path, slug: str) -> bool:
    try:
        paths = [_json(runtime_dir, slug), _xml(runtime_dir, slug)]
    except ValueError:
        return False
    existed = paths[0].exists()
    for p in paths:
        p.unlink(missing_ok=True)
    return existed


def set_breaker_rules(runtime_dir: Path, slug: str, rules: list[BreakerRule]) -> GuideProfile:
    profile = load_guide(runtime_dir, slug)
    if profile is None:
        raise KeyError(slug)
    profile = profile.model_copy(update={"breaker_rules": rules})
    _write(runtime_dir, profile)
    return profile


def _read_assignments(runtime_dir: Path) -> dict:
    path = _dir(runtime_dir) / _ASSIGNMENTS
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def get_assignment(runtime_dir: Path, character_id: str) -> tuple[str | None, str | None]:
    entry = _read_assignments(runtime_dir).get(character_id)
    if not entry or load_guide(runtime_dir, entry.get("guide_slug") or "") is None:
        return None, None
    return entry["guide_slug"], entry.get("stage_override")


def set_assignment(
    runtime_dir: Path, character_id: str, guide_slug: str | None, stage_override: str | None
) -> None:
    data = _read_assignments(runtime_dir)
    data[character_id] = {"guide_slug": guide_slug, "stage_override": stage_override}
    atomic_write_file(
        _dir(runtime_dir) / _ASSIGNMENTS, json.dumps(data, indent=2).encode("utf-8")
    )
