"""Tests for the adb enums."""

import pytest

import android_mcp.adb as adb


@pytest.mark.unit
class TestKeyCodeParse:
    """Tests for KeyCode.parse."""

    @pytest.mark.parametrize(
        ("name", "key"),
        [
            ("back", adb.KeyCode.BACK),
            ("BACK", adb.KeyCode.BACK),
            ("  Home ", adb.KeyCode.HOME),
            ("volume_up", adb.KeyCode.VOLUME_UP),
            ("Volume Up", adb.KeyCode.VOLUME_UP),
            ("volume-down", adb.KeyCode.VOLUME_DOWN),
            ("volume mute", adb.KeyCode.VOLUME_MUTE),
            ("enter", adb.KeyCode.ENTER),
            ("power", adb.KeyCode.POWER),
            ("camera", adb.KeyCode.CAMERA),
            ("menu", adb.KeyCode.MENU),
            ("search", adb.KeyCode.SEARCH),
            ("tab", adb.KeyCode.TAB),
            ("dpad_center", adb.KeyCode.DPAD_CENTER),
        ],
    )
    def test_names_in_any_case_or_spacing(self, name, key):
        """Case, spaces and hyphens do not matter."""
        assert adb.KeyCode.parse(name) is key

    @pytest.mark.parametrize(
        ("alias", "key"),
        [
            ("up", adb.KeyCode.DPAD_UP),
            ("down", adb.KeyCode.DPAD_DOWN),
            ("left", adb.KeyCode.DPAD_LEFT),
            ("right", adb.KeyCode.DPAD_RIGHT),
            ("center", adb.KeyCode.DPAD_CENTER),
            ("recent", adb.KeyCode.APP_SWITCH),
            ("Recents", adb.KeyCode.APP_SWITCH),
            ("del", adb.KeyCode.DELETE),
            ("delete", adb.KeyCode.DELETE),
        ],
    )
    def test_the_original_tools_short_names(self, alias, key):
        """The names the original Android-MCP accepted still work."""
        assert adb.KeyCode.parse(alias) is key

    def test_unknown_key_lists_the_known_ones(self):
        """The error names what was asked for and what is allowed."""
        with pytest.raises(ValueError, match="unknown key 'nope'") as info:
            adb.KeyCode.parse("nope")

        assert "volume_up" in str(info.value) and "app_switch" in str(info.value)

    def test_every_member_can_be_found_by_its_own_name(self):
        """No key is unreachable."""
        for key in adb.KeyCode:
            assert adb.KeyCode.parse(key.name.lower()) is key
