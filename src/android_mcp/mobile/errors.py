"""Exceptions raised by the mobile service."""


class MobileError(RuntimeError):
    """No device is connected, or the one asked for cannot be used.

    The message says what is wrong and, where it helps, which devices are available.
    """


class ElementNotFoundError(MobileError):
    """An element that was waited for never appeared on the screen."""
