"""Core data models and dataclasses for Windows Power Explorer."""

from dataclasses import dataclass, field
from enum import Enum


class ControlType(Enum):
    """Inferred widget control type based on setting metadata."""

    ENUM = "enum"          # Discrete options -> CTkOptionMenu
    TOGGLE = "toggle"      # Exactly 0..1 range -> CTkSwitch
    RANGE = "range"        # Continuous/stepped range -> CTkSlider
    READONLY = "readonly"  # Unreadable bounds or fixed DWORD -> CTkLabel


@dataclass(frozen=True)
class SettingValueChoice:
    """Discrete choice option for enumerated power settings."""

    value_index: int
    friendly_name: str
    description: str


@dataclass
class PowerSetting:
    """Flattened UI representation of an individual power setting."""

    guid: str
    subgroup_guid: str
    friendly_name: str
    description: str
    control_type: ControlType

    is_hidden: bool
    is_policy_locked: bool
    is_degraded: bool
    has_friendly_name: bool

    value_units: str
    min_value: int | None
    max_value: int | None
    value_increment: int | None

    ac_value: int | None
    dc_value: int | None

    choices: list[SettingValueChoice] = field(default_factory=list)
    hazard_note: str | None = None


@dataclass
class PowerSubgroup:
    """Category subgroup containing a list of power settings."""

    guid: str
    friendly_name: str
    description: str
    is_hidden: bool
    settings: list[PowerSetting] = field(default_factory=list)


@dataclass
class PowerScheme:
    """Complete power scheme definition."""

    guid: str
    friendly_name: str
    description: str
    is_active: bool
    is_base_default: bool
    subgroups: list[PowerSubgroup] = field(default_factory=list)


@dataclass(frozen=True)
class OverlayInfo:
    """Windows 11 power mode overlay information (read-only)."""

    guid: str
    friendly_name: str
    is_balanced: bool


@dataclass
class EnumStats:
    """Summary statistics for power setting enumeration."""

    subgroup_count: int = 0
    setting_count: int = 0
    degraded_count: int = 0
    policy_locked_count: int = 0
    elapsed_ms: int = 0


@dataclass(frozen=True)
class ValueChange:
    """Single setting modification for undo tracking (frozen, in-memory only)."""

    scheme_guid: str
    subgroup_guid: str
    setting_guid: str
    rail: str  # "ac" or "dc"
    previous_value: int
    new_value: int


@dataclass(frozen=True)
class SettingDiff:
    """One row of a scheme comparison."""

    setting_guid: str
    subgroup_guid: str
    friendly_name: str
    ac_left: int | None
    ac_right: int | None
    dc_left: int | None
    dc_right: int | None

    @property
    def differs(self) -> bool:
        """Return True if any rail differs between left and right."""
        return (self.ac_left != self.ac_right) or (self.dc_left != self.dc_right)


@dataclass(frozen=True)
class SettingCatalogEntry:
    """Scheme-invariant catalog entry for a single power setting (ADR-012)."""

    guid: str
    subgroup_guid: str
    friendly_name: str
    description: str
    control_type: ControlType
    min_value: int | None
    max_value: int | None
    value_increment: int | None
    value_units: str
    choices: tuple[SettingValueChoice, ...]
    is_hidden: bool
    is_policy_locked: bool
    is_degraded: bool


@dataclass(frozen=True)
class SubgroupCatalogEntry:
    """Scheme-invariant catalog entry for a subgroup (ADR-012)."""

    guid: str
    friendly_name: str
    description: str
    is_hidden: bool
    settings: tuple[SettingCatalogEntry, ...]


@dataclass(frozen=True)
class SettingCatalog:
    """Scheme-invariant setting catalog across all subgroups (ADR-012)."""

    subgroups: tuple[SubgroupCatalogEntry, ...]
    by_guid: dict[str, SettingCatalogEntry]
    subgroup_by_guid: dict[str, SubgroupCatalogEntry]


@dataclass
class SchemeValues:
    """Per-scheme configured values and personality-keyed defaults."""

    scheme_guid: str
    personality_guid: str
    ac: dict[str, int | None]
    dc: dict[str, int | None]
    ac_default: dict[str, int | None]
    dc_default: dict[str, int | None]
