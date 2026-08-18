"""Presentational Metadata Loader (Issue #32).

Loads optional UI metadata from data/ (essentials, reboot_required, doc_links).
Each file is independently optional and degrades gracefully if missing or invalid (ADR-005, NFR-4).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_data_dir(data_dir: Path | str | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    # Default to repo/app data/ directory
    return Path(__file__).resolve().parent.parent / "data"


def load_essentials(data_dir: Path | str | None = None) -> list[dict]:
    """Load curated essentials list from essentials.json.

    Returns list of dicts with 'guid', 'name', 'category', 'subgroup_guid'.
    Returns empty list if file is missing, empty, or malformed.
    """
    path = _get_data_dir(data_dir) / "essentials.json"
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "settings" in data and isinstance(data["settings"], list):
            return data["settings"]
        elif isinstance(data, list):
            return data
    except Exception as exc:
        logger.warning("Failed to load essentials.json, degrading gracefully: %s", exc)
    return []


def load_essentials_guids(data_dir: Path | str | None = None) -> set[str]:
    """Load set of lowercase setting GUIDs marked as essential."""
    settings = load_essentials(data_dir)
    guids = set()
    for s in settings:
        if isinstance(s, dict) and "guid" in s:
            guids.add(str(s["guid"]).lower())
        elif isinstance(s, str):
            guids.add(s.lower())
    return guids


def load_reboot_required(data_dir: Path | str | None = None) -> set[str]:
    """Load set of lowercase GUIDs requiring reboot from reboot_required.json.

    Returns empty set if file is missing or malformed.
    """
    path = _get_data_dir(data_dir) / "reboot_required.json"
    if not path.is_file():
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "guids" in data and isinstance(data["guids"], list):
            return {str(g).lower() for g in data["guids"]}
        elif isinstance(data, list):
            return {str(g).lower() for g in data}
    except Exception as exc:
        logger.warning("Failed to load reboot_required.json, degrading gracefully: %s", exc)
    return set()


def load_doc_links(data_dir: Path | str | None = None) -> dict[str, str]:
    """Load map of setting GUID (lowercase) -> doc URL from doc_links.json.

    Returns empty dict if file is missing or malformed.
    """
    path = _get_data_dir(data_dir) / "doc_links.json"
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "links" in data and isinstance(data["links"], dict):
            return {str(k).lower(): str(v) for k, v in data["links"].items()}
        elif isinstance(data, dict):
            return {str(k).lower(): str(v) for k, v in data.items() if k != "version" and k != "description"}
    except Exception as exc:
        logger.warning("Failed to load doc_links.json, degrading gracefully: %s", exc)
    return {}
