"""Mobile service: connects to a device, reads its screen and acts on it.

Usage:
    from android_mcp.mobile import Mobile

    mobile = Mobile()
    mobile.connect()
    state = mobile.get_state(use_vision=True)
    print(state.to_string())
    mobile.tap(*state.elements[0].center)
"""

from .errors import ElementNotFoundError, MobileError
from .service import Mobile, normalize_wifi_address, pick_device
from .views import MobileState, format_elements

__all__ = [
    "ElementNotFoundError",
    "Mobile",
    "MobileError",
    "MobileState",
    "format_elements",
    "normalize_wifi_address",
    "pick_device",
]
