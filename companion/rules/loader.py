"""YAML guide rules loader for declarative build and transition rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

from companion.rules.schema import GuideRule

DEFAULT_GUIDE_RULES_PATH: Path = (
    Path(__file__).resolve().parents[2] / "data" / "source" / "guide_rules.yaml"
)


def load_guide_rules(path: str | Path | None = None) -> list[GuideRule]:
    """Parse and validate declarative rules from YAML fixture into GuideRule models.

    Ensures explicit transition roles are validated and rules lacking supported
    observability paths are marked as evaluable=False.
    """
    target_path = Path(path) if path is not None else DEFAULT_GUIDE_RULES_PATH
    if not target_path.is_file():
        raise FileNotFoundError(f"Guide rules file not found: {target_path}")

    raw_text = target_path.read_text(encoding="utf-8")
    raw_data: Any = yaml.safe_load(raw_text)

    if isinstance(raw_data, dict) and "rules" in raw_data:
        rule_entries = raw_data["rules"]
    elif isinstance(raw_data, list):
        rule_entries = raw_data
    else:
        raise ValueError(
            f"Invalid rules format in {target_path}: expected dictionary with 'rules' or list of rules"
        )

    if not isinstance(rule_entries, list):
        raise ValueError(f"Rules entry in {target_path} must be a list of rule specifications")

    rules: list[GuideRule] = []
    for entry in rule_entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Each rule in {target_path} must be a dictionary, got: {type(entry)}")
        rule = GuideRule.model_validate(entry)
        rules.append(rule)

    return rules
