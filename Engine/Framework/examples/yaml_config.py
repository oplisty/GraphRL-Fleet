from __future__ import annotations

import argparse
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    yaml = None
    _YAML_IMPORT_ERROR = exc
else:
    _YAML_IMPORT_ERROR = None


def parse_args_with_yaml(parser: argparse.ArgumentParser) -> argparse.Namespace:
    """Parse CLI args with optional YAML config override.

    Expected contract:
    - parser must define `--config`
    - YAML file should contain a flat mapping where keys are argparse `dest` names
    - CLI args still have highest priority over YAML defaults
    """
    pre_args, _ = parser.parse_known_args()
    config_path = getattr(pre_args, "config", None)
    if config_path:
        apply_yaml_defaults(parser, config_path)
    return parser.parse_args()


def apply_yaml_defaults(parser: argparse.ArgumentParser, config_path: str) -> None:
    if yaml is None:  # pragma: no cover
        raise RuntimeError(
            "PyYAML is required for --config but is not installed. "
            f"Import error: {_YAML_IMPORT_ERROR}"
        )

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    if not isinstance(payload, dict):
        raise ValueError(f"YAML config must be a mapping(dict), got: {type(payload).__name__}")

    valid_keys = {action.dest for action in parser._actions}
    unknown_keys = sorted(set(payload) - valid_keys)
    if unknown_keys:
        raise ValueError(
            f"Unknown config keys in {path}: {unknown_keys}. "
            "Please use argparse destination names (snake_case)."
        )

    parser.set_defaults(**payload)
