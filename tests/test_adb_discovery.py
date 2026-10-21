"""Tests for locating the adb binary. Real filesystem, fake adb files, no device needed."""

import os
from pathlib import Path

import pytest

import android_mcp.adb as adb
from android_mcp.adb import core


def _make_adb(directory: Path) -> str:
    """Create an executable fake adb in ``directory`` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / core._ADB_EXE
    exe.write_text("")
    exe.chmod(0o755)
    return str(exe)


def _make_sdk(root: Path) -> str:
    """Create a fake SDK at ``root`` with adb in ``platform-tools`` and return its path."""
    return _make_adb(root / "platform-tools")


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    """No overrides, an empty PATH, a throwaway home and cwd, no system bin directories."""
    for name in (adb.OVERRIDE_VAR, "ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(core, "_POSIX_BIN_DIRS", ())
    monkeypatch.chdir(tmp_path)  # Windows searches the cwd before PATH
    return tmp_path


@pytest.mark.unit
class TestOverride:
    """Tests for the ANDROID_MCP_ADB_PATH override."""

    def test_wins_over_path_and_sdk(self, clean_env, monkeypatch):
        """The override beats both PATH and an SDK."""
        exe = _make_adb(clean_env / "explicit")
        _make_adb(clean_env / "tools")
        _make_sdk(clean_env / "sdk")
        monkeypatch.setenv("PATH", str(clean_env / "tools"))
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
        monkeypatch.setenv(adb.OVERRIDE_VAR, exe)

        assert adb.find_adb() == exe

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_is_ignored(self, clean_env, monkeypatch, blank):
        """A blank value, as MCP hosts pass for unset options, counts as unset."""
        exe = _make_sdk(clean_env / "sdk")
        monkeypatch.setenv(adb.OVERRIDE_VAR, blank)
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))

        assert adb.find_adb() == exe

    @pytest.mark.parametrize("bad", ["missing", "."])
    def test_unusable_raises_instead_of_falling_back(self, clean_env, monkeypatch, bad):
        """A missing file or a directory fails visibly, even when another adb exists."""
        _make_sdk(clean_env / "sdk")
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
        monkeypatch.setenv(adb.OVERRIDE_VAR, str(clean_env / "sdk" / bad))

        with pytest.raises(adb.AdbNotFoundError, match=adb.OVERRIDE_VAR):
            adb.find_adb()


@pytest.mark.unit
class TestPath:
    """Tests for finding adb on PATH."""

    def test_path_is_used(self, clean_env, monkeypatch):
        """An adb on PATH is found."""
        exe = _make_adb(clean_env / "tools")
        monkeypatch.setenv("PATH", str(clean_env / "tools"))

        assert os.path.samefile(adb.find_adb(), exe)

    def test_path_wins_over_sdk(self, clean_env, monkeypatch):
        """PATH comes before the SDK, so an install that already works keeps being used."""
        on_path = _make_adb(clean_env / "tools")
        _make_sdk(clean_env / "sdk")
        monkeypatch.setenv("PATH", str(clean_env / "tools"))
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))

        assert os.path.samefile(adb.find_adb(), on_path)


@pytest.mark.unit
class TestSdkLocations:
    """Tests for finding adb in an Android SDK."""

    def test_android_home(self, clean_env, monkeypatch):
        """ANDROID_HOME points at the SDK."""
        exe = _make_sdk(clean_env / "sdk")
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))

        assert adb.find_adb() == exe

    def test_android_sdk_root(self, clean_env, monkeypatch):
        """ANDROID_SDK_ROOT points at the SDK."""
        exe = _make_sdk(clean_env / "sdk")
        monkeypatch.setenv("ANDROID_SDK_ROOT", str(clean_env / "sdk"))

        assert adb.find_adb() == exe

    def test_android_home_wins_over_sdk_root(self, clean_env, monkeypatch):
        """When both are set and both have adb, ANDROID_HOME is used."""
        first = _make_sdk(clean_env / "first")
        _make_sdk(clean_env / "second")
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "first"))
        monkeypatch.setenv("ANDROID_SDK_ROOT", str(clean_env / "second"))

        assert adb.find_adb() == first

    def test_windows_default_location(self, clean_env, monkeypatch):
        """With nothing configured, %LOCALAPPDATA%\\Android\\Sdk is searched."""
        exe = _make_sdk(clean_env / "local" / "Android" / "Sdk")
        monkeypatch.setenv("LOCALAPPDATA", str(clean_env / "local"))

        assert adb.find_adb() == exe

    @pytest.mark.parametrize(
        "parts", [("Library", "Android", "sdk"), ("Android", "Sdk")], ids=["macos", "linux"]
    )
    def test_default_locations_under_home(self, clean_env, parts):
        """With nothing configured, the macOS and Linux Android Studio locations are searched."""
        exe = _make_sdk(clean_env.joinpath("home", *parts))

        assert adb.find_adb() == exe

    def test_posix_bin_dirs(self, clean_env, monkeypatch):
        """Homebrew and /usr/local style directories are searched last."""
        exe = _make_adb(clean_env / "homebrew")
        monkeypatch.setattr(core, "_POSIX_BIN_DIRS", (clean_env / "homebrew",))

        assert adb.find_adb() == exe

    def test_blank_sdk_variables_are_dropped(self, clean_env, monkeypatch):
        """Blank ANDROID_HOME / ANDROID_SDK_ROOT do not add the current directory to the search."""
        monkeypatch.setenv("ANDROID_HOME", "  ")
        monkeypatch.setenv("ANDROID_SDK_ROOT", "")

        assert Path("") not in core._sdk_roots()


@pytest.mark.unit
class TestNotFound:
    """Tests for when no adb can be located."""

    def test_names_what_was_searched(self, clean_env, monkeypatch):
        """The error lists the override variable, PATH and every SDK directory tried."""
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))

        with pytest.raises(adb.AdbNotFoundError) as info:
            adb.find_adb()

        message = str(info.value)
        assert adb.OVERRIDE_VAR in message
        assert str(clean_env / "empty-path") in message
        assert str(clean_env / "sdk" / "platform-tools") in message

    @pytest.mark.skipif(os.name == "nt", reason="Windows has no executable bit to withhold")
    def test_non_executable_file_is_not_accepted(self, clean_env, monkeypatch):
        """A file without the executable bit is not treated as adb."""
        Path(_make_sdk(clean_env / "sdk")).chmod(0o644)
        monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))

        with pytest.raises(adb.AdbNotFoundError):
            adb.find_adb()
