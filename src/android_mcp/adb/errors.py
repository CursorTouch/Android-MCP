"""Exceptions raised by the adb layer."""

from collections.abc import Sequence


class AdbError(RuntimeError):
    """Base class for every error the adb layer raises."""


class AdbNotFoundError(AdbError):
    """No usable adb binary could be located."""


class AdbCommandError(AdbError):
    """An adb command exited non-zero, or did not finish in time.

    Attributes:
        command: The full command line that was run.
        returncode: The exit status, or ``None`` when the command timed out.
        detail: What adb reported on stderr, or a description of the timeout.
    """

    def __init__(self, command: Sequence[str], returncode: int | None, detail: str):
        self.command = list(command)
        self.returncode = returncode
        self.detail = detail
        status = "timed out" if returncode is None else f"exited with {returncode}"
        super().__init__(f"{' '.join(self.command)} {status}: {detail}")


class ScreenNotIdleError(AdbError):
    """The screen never stopped changing, so the UI hierarchy could not be dumped.

    ``uiautomator dump`` waits for a second with no UI events and gives up after ten. A screen
    that animates or updates continuously never has one, so this lasts as long as that does. A
    screenshot still works, and so does tapping by coordinates.
    """
