"""Windows Power Explorer core engine."""

from core.__version__ import __version__, __version_info__
from core.catalog import build_catalog
from core.compare import compare_schemes, get_modified_settings
from core.controller import AppController
from core.errors import (
    ElevationDeclinedError,
    ElevationRequiredError,
    PolicyLockedError,
    PowerApiError,
    PowerExplorerError,
    PresetValidationError,
    SchemeNotFoundError,
    SettingNotFoundError,
    ValueOutOfBoundsError,
    user_message,
)
from core.models import (
    ControlType,
    EnumStats,
    OverlayInfo,
    PowerScheme,
    PowerSetting,
    PowerSubgroup,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
    SettingDiff,
    SettingValueChoice,
    SubgroupCatalogEntry,
    ValueChange,
)
from core.power_manager import PowerManager
from core.state import AppState
from core.values import (
    assemble_power_scheme,
    assemble_power_setting,
    load_scheme_values,
)
from core.win32_bindings import (
    GUID,
    is_elevated,
    is_overlay_supported,
    parse_guid,
    verify_bindings,
)

__all__ = [
    "__version__",
    "__version_info__",
    "PowerExplorerError",
    "PowerApiError",
    "ElevationRequiredError",
    "ElevationDeclinedError",
    "ValueOutOfBoundsError",
    "PolicyLockedError",
    "SchemeNotFoundError",
    "SettingNotFoundError",
    "PresetValidationError",
    "user_message",
    "ControlType",
    "SettingValueChoice",
    "PowerSetting",
    "PowerSubgroup",
    "PowerScheme",
    "OverlayInfo",
    "EnumStats",
    "ValueChange",
    "SettingDiff",
    "SettingCatalogEntry",
    "SubgroupCatalogEntry",
    "SettingCatalog",
    "SchemeValues",
    "AppState",
    "AppController",
    "GUID",
    "parse_guid",
    "is_elevated",
    "is_overlay_supported",
    "verify_bindings",
    "PowerManager",
    "build_catalog",
    "load_scheme_values",
    "assemble_power_setting",
    "assemble_power_scheme",
    "compare_schemes",
    "get_modified_settings",
]
