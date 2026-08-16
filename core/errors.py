"""Exception hierarchy and Win32 error code mappings."""

_MESSAGES = {
    2: "That power scheme or setting no longer exists.",
    5: "This change needs Administrator permission.",
    13: "Windows rejected that value for this setting.",
    87: "Windows rejected that value for this setting.",
    1223: "Change cancelled.",
}


def user_message(code: int, action: str = "applying your change") -> str:
    """Map a Win32 return code to a user-friendly message."""
    return _MESSAGES.get(
        code, f"Windows reported an unexpected error (code {code}) while {action}."
    )


class PowerExplorerError(Exception):
    """Base exception for all Windows Power Explorer errors."""


class PowerApiError(PowerExplorerError):
    """Raised when a PowrProf.dll or Win32 API call returns a nonzero status."""

    def __init__(self, function: str, code: int, context: str = ""):
        self.function = function
        self.code = code
        self.context = context
        msg = f"{function} failed with {code}: {user_message(code)}"
        if context:
            msg += f" (Context: {context})"
        super().__init__(msg)


class ElevationRequiredError(PowerExplorerError):
    """Raised when an operation requires Administrator privileges."""


class ElevationDeclinedError(PowerExplorerError):
    """Raised when the user dismisses the UAC consent prompt."""


class ValueOutOfBoundsError(PowerExplorerError):
    """Raised when a value violates the setting's declared min/max/increment bounds."""


class PolicyLockedError(PowerExplorerError):
    """Raised when Group Policy forbids modifying a power setting."""


class SchemeNotFoundError(PowerExplorerError):
    """Raised when a power scheme GUID or name does not exist."""


class SettingNotFoundError(PowerExplorerError):
    """Raised when a power setting GUID does not exist."""


class PresetValidationError(PowerExplorerError):
    """Raised when an imported JSON preset fails schema or semantic validation."""
