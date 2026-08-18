"""Centralized Application State for Windows Power Explorer (Issue #17).

AppState is held by AppController; the UI renders from it and never holds
authoritative state of its own. All derived views (modified status, filtering,
scheme selection) are computed dynamically from this state.
"""

from dataclasses import dataclass, field
from typing import Iterator

from core.models import (
    OverlayInfo,
    PowerScheme,
    PowerSetting,
    PowerSubgroup,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
    SettingDiff,
    ValueChange,
)


@dataclass
class AppState:
    """Centralized application state model.

    Holds authoritative state for both load phases, filtering, system context,
    pending visibility edits, single-level undo, user preferences, and worker coordination.
    """

    # Phase 1 — scheme-invariant catalog (rebuilt rarely)
    catalog: SettingCatalog | None = None

    # Phase 2 — per-scheme values & active selection
    schemes: list[PowerScheme] = field(default_factory=list)
    active_scheme_guid: str | None = None
    selected_scheme_guid: str | None = None
    values: SchemeValues | None = None
    compare_scheme_guid: str | None = None  # Second scheme in compare view

    # Filtering & navigation
    selected_category: str = "all"  # Subgroup GUID, "all", "essentials", "favorites"
    search_query: str = ""
    show_modified_only: bool = False

    # System context
    overlay: OverlayInfo | None = None
    has_battery: bool = True  # If False, DC column is hidden entirely
    is_elevated: bool = False

    # Pending & undo
    pending_visibility: dict[tuple[str, str], bool] = field(default_factory=dict)  # (subgroup_guid, setting_guid) -> is_visible
    last_change: ValueChange | None = None  # Single-level undo (REQ-11.1)

    # Preferences (persisted to ui-state.json)
    appearance_mode: str = "System"  # "Light" | "Dark" | "System"
    favorites: set[tuple[str, str]] = field(default_factory=set)  # set of (subgroup_guid, setting_guid)

    # Worker coordination
    enumeration_generation: int = 0
    active_worker_count: int = 0  # Drives drain loop lifecycle

    # --- Derived Properties & Computed Helpers ---

    @property
    def is_apply_enabled(self) -> bool:
        """Return True if there are pending visibility changes to apply."""
        return bool(self.pending_visibility)

    @property
    def active_scheme(self) -> PowerScheme | None:
        """Return the PowerScheme object corresponding to active_scheme_guid."""
        if not self.active_scheme_guid:
            return None
        for s in self.schemes:
            if s.guid.lower() == self.active_scheme_guid.lower():
                return s
        return None

    @property
    def selected_scheme(self) -> PowerScheme | None:
        """Return the PowerScheme object corresponding to selected_scheme_guid."""
        if not self.selected_scheme_guid:
            return None
        for s in self.schemes:
            if s.guid.lower() == self.selected_scheme_guid.lower():
                return s
        return None

    @property
    def compare_scheme(self) -> PowerScheme | None:
        """Return the PowerScheme object corresponding to compare_scheme_guid."""
        if not self.compare_scheme_guid:
            return None
        for s in self.schemes:
            if s.guid.lower() == self.compare_scheme_guid.lower():
                return s
        return None

    def is_setting_modified(self, setting_guid: str) -> bool:
        """Determine if a setting's value differs from its personality default."""
        if not self.values:
            return False
        key = setting_guid.lower()
        ac_val = self.values.ac.get(key)
        ac_def = self.values.ac_default.get(key)
        dc_val = self.values.dc.get(key)
        dc_def = self.values.dc_default.get(key)

        # If no default is known, it is not considered modified
        if ac_def is None and dc_def is None:
            return False

        if ac_def is not None and ac_val is not None and ac_val != ac_def:
            return True
        if dc_def is not None and dc_val is not None and dc_val != dc_def:
            return True
        return False

    def is_favorite(self, subgroup_guid: str, setting_guid: str) -> bool:
        """Check if a setting is in favorites."""
        return (subgroup_guid.lower(), setting_guid.lower()) in {
            (sub.lower(), set_g.lower()) for sub, set_g in self.favorites
        }

    def toggle_favorite(self, subgroup_guid: str, setting_guid: str) -> bool:
        """Toggle a setting in favorites. Returns True if now favorite, False if removed."""
        pair = (subgroup_guid.lower(), setting_guid.lower())
        existing = {
            (sub.lower(), set_g.lower()): (sub, set_g) for sub, set_g in self.favorites
        }
        if pair in existing:
            self.favorites.remove(existing[pair])
            return False
        else:
            self.favorites.add((subgroup_guid, setting_guid))
            return True

    def clear_undo(self) -> None:
        """Clear single-level undo on scheme switch, refresh, or import (REQ-11.2)."""
        self.last_change = None

    def reset_transient_filters(self) -> None:
        """Reset search and category filter to default view."""
        self.selected_category = "all"
        self.search_query = ""
        self.show_modified_only = False

    def matches_search(self, setting: SettingCatalogEntry) -> bool:
        """Check if a setting matches the current search query."""
        if not self.search_query:
            return True
        query = self.search_query.strip().lower()
        if not query:
            return True

        if query in setting.friendly_name.lower():
            return True
        if query in setting.description.lower():
            return True
        if query in setting.guid.lower():
            return True
        for choice in setting.choices:
            if query in choice.friendly_name.lower():
                return True
        return False

    def get_filtered_settings(
        self,
        essentials_guids: set[str] | None = None,
    ) -> list[SettingCatalogEntry]:
        """Compute the list of visible settings matching all active filters."""
        if not self.catalog:
            return []

        results: list[SettingCatalogEntry] = []
        cat = self.selected_category.lower()

        for sub in self.catalog.subgroups:
            # Subgroup category filter check
            if cat not in ("all", "essentials", "favorites") and sub.guid.lower() != cat:
                continue

            for setting in sub.settings:
                # Category filter checks
                if cat == "favorites" and not self.is_favorite(sub.guid, setting.guid):
                    continue
                if cat == "essentials" and essentials_guids and setting.guid.lower() not in {g.lower() for g in essentials_guids}:
                    continue

                # Modified filter check
                if self.show_modified_only and not self.is_setting_modified(setting.guid):
                    continue

                # Search query check
                if not self.matches_search(setting):
                    continue

                results.append(setting)

        return results
