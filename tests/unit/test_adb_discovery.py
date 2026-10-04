"""Unit tests for adb discovery. Run with: uv run --with pytest pytest tests"""
import os
import stat
from pathlib import Path
from typing import Iterator

import pytest

from android_mcp.mobile import adb

DEVICES_OUTPUT = "List of devices attached\nemulator-5554\tdevice\n"


def _make_adb(directory: Path, output: str = "") -> str:
    """Create an executable fake adb at <directory>/platform-tools/adb and return its path."""
    platform_tools = directory / "platform-tools"
    platform_tools.mkdir(parents=True, exist_ok=True)
    exe = platform_tools / adb._ADB_EXE
    exe.write_text(f"#!/bin/sh\nprintf '%s' '{output}'\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return str(exe)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Isolate discovery from the real machine: empty PATH, no SDK variables, fake HOME."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    for name in (*adb.OVERRIDE_VARS, "ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(adb, "_POSIX_BIN_DIRS", ())
    yield tmp_path
    # adb_path() publishes into os.environ; monkeypatch only restores keys it saw set.
    os.environ.pop("ADBUTILS_ADB_PATH", None)


def test_server_override_wins_over_everything(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = _make_adb(clean_env / "explicit")
    other = _make_adb(clean_env / "other")
    monkeypatch.setenv("ANDROID_MCP_ADB_PATH", exe)
    monkeypatch.setenv("ADBUTILS_ADB_PATH", other)
    monkeypatch.setenv("PATH", os.path.dirname(other))
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "other"))
    assert adb.find_adb() == exe


def test_adbutils_override_wins_over_path_and_sdk(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = _make_adb(clean_env / "explicit")
    other = _make_adb(clean_env / "other")
    monkeypatch.setenv("ADBUTILS_ADB_PATH", exe)
    monkeypatch.setenv("PATH", os.path.dirname(other))
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "other"))
    assert adb.find_adb() == exe


def test_blank_env_values_are_ignored(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP hosts render unset user_config fields as empty strings."""
    exe = _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_MCP_ADB_PATH", "")
    monkeypatch.setenv("ADBUTILS_ADB_PATH", "  ")
    monkeypatch.setenv("ANDROID_SDK_ROOT", "   ")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert adb.find_adb() == exe


@pytest.mark.parametrize("bad", ["missing-file", "platform-tools"])
def test_bad_override_raises_instead_of_falling_through(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    monkeypatch.setenv("ANDROID_MCP_ADB_PATH", str(clean_env / "sdk" / bad))
    with pytest.raises(adb.AdbNotFoundError, match="ANDROID_MCP_ADB_PATH"):
        adb.find_adb()


def test_path_lookup(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = _make_adb(clean_env / "tools")
    monkeypatch.setenv("PATH", os.path.dirname(exe))
    assert adb.find_adb() == exe


def test_path_beats_sdk(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    on_path = _make_adb(clean_env / "tools")
    _make_adb(clean_env / "sdk")
    monkeypatch.setenv("PATH", os.path.dirname(on_path))
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert adb.find_adb() == on_path


def test_android_home_platform_tools(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert adb.find_adb() == exe


def test_android_sdk_root_platform_tools(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(clean_env / "sdk"))
    assert adb.find_adb() == exe


def test_missing_android_home_falls_through(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "not-there"))
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(clean_env / "sdk"))
    assert adb.find_adb() == exe


def test_default_sdk_location_under_home(clean_env: Path) -> None:
    exe = _make_adb(clean_env / "home" / "Library" / "Android" / "sdk")
    assert adb.find_adb() == exe


def test_default_sdk_location_under_localappdata(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = _make_adb(clean_env / "local" / "Android" / "Sdk")
    monkeypatch.setenv("LOCALAPPDATA", str(clean_env / "local"))
    assert adb.find_adb() == exe


def test_linux_default_sdk_location(clean_env: Path) -> None:
    exe = _make_adb(clean_env / "home" / "Android" / "Sdk")
    assert adb.find_adb() == exe


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_localappdata_is_skipped(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", value)
    assert all("Android" not in root or "home" in root for root in adb.sdk_roots())
    assert adb.find_adb() is None


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_symlinked_sdk_root(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = _make_adb(clean_env / "real-sdk")
    (clean_env / "sdk-link").symlink_to(clean_env / "real-sdk", target_is_directory=True)
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk-link"))
    assert adb.find_adb() == str(clean_env / "sdk-link" / "platform-tools" / adb._ADB_EXE)
    assert os.path.samefile(adb.find_adb(), exe)


def test_blank_server_override_keeps_inherited_adbutils_override(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty extension field must not hide an ADBUTILS_ADB_PATH the user already set."""
    exe = _make_adb(clean_env / "inherited")
    _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_MCP_ADB_PATH", "")
    monkeypatch.setenv("ADBUTILS_ADB_PATH", exe)
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert adb.find_adb() == exe


def test_posix_bin_dirs_are_probed_last(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = _make_adb(clean_env / "sdk")
    brew = _make_adb(clean_env / "brew")
    monkeypatch.setattr(adb, "_POSIX_BIN_DIRS", (os.path.dirname(brew),))
    assert adb.find_adb() == brew
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert adb.find_adb() == sdk


def test_duplicate_roots_are_collapsed(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    monkeypatch.setenv("ANDROID_SDK_ROOT", str(clean_env / "sdk"))
    assert adb.sdk_roots().count(str(clean_env / "sdk")) == 1


def test_adb_path_publishes_to_adbutils(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert adb.adb_path() == exe
    assert os.environ["ADBUTILS_ADB_PATH"] == exe


def test_not_found_lists_where_it_looked(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "missing-sdk"))
    with pytest.raises(adb.AdbNotFoundError) as excinfo:
        adb.adb_path()
    message = str(excinfo.value)
    assert "ANDROID_MCP_ADB_PATH" in message
    assert str(clean_env / "empty-bin") in message  # the PATH the server actually saw
    assert os.path.join(str(clean_env / "missing-sdk"), "platform-tools") in message
    assert "ADBUTILS_ADB_PATH" not in os.environ


def test_non_executable_file_is_skipped(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    monkeypatch.setattr(os, "access", lambda path, mode: False)
    assert adb.find_adb() is None
    assert exe  # the file exists; only the permission check rejected it


@pytest.mark.skipif(os.name == "nt", reason="os.access(X_OK) is existence-only on Windows")
def test_non_executable_file_is_skipped_by_the_real_permission_check(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = _make_adb(clean_env / "sdk")
    os.chmod(exe, stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert adb.find_adb() is None


# --- the production paths in mobile/service.py -------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="fake adb is a shell script")
def test_list_devices_uses_sdk_adb_with_bare_path(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from android_mcp.mobile.service import Mobile

    _make_adb(clean_env / "sdk", output=DEVICES_OUTPUT)
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    assert Mobile.list_devices() == [("emulator-5554", "device")]


@pytest.mark.skipif(os.name == "nt", reason="fake adb is a shell script")
def test_adb_connect_uses_resolved_adb(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from android_mcp.mobile.service import Mobile

    _make_adb(clean_env / "sdk", output="connected to 192.168.1.10:5555")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    Mobile.adb_connect("192.168.1.10:5555")  # raises if adb could not be run


@pytest.mark.parametrize("inherited", [None, "", "   "])
def test_connect_still_works_when_discovery_finds_nothing(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, inherited: "str | None"
) -> None:
    """adbutils may still reach a running adb server, or use its bundled adb on Windows.

    A blank inherited ADBUTILS_ADB_PATH is removed, because adbutils would run it verbatim.
    """
    from android_mcp.mobile import service

    if inherited is not None:
        monkeypatch.setenv("ADBUTILS_ADB_PATH", inherited)
    seen = {}

    def fake_connect(serial: str) -> object:
        seen["env"] = os.environ.get("ADBUTILS_ADB_PATH")
        return type("FakeDevice", (), {"info": {}})()

    monkeypatch.setattr(service.u2, "connect", fake_connect)
    mobile = service.Mobile()
    mobile.connect("emulator-5554")
    assert mobile.is_connected
    assert seen["env"] is None


def test_connect_publishes_discovered_adb(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from android_mcp.mobile import service

    exe = _make_adb(clean_env / "sdk")
    monkeypatch.setenv("ANDROID_HOME", str(clean_env / "sdk"))
    seen = {}

    def fake_connect(serial: str) -> object:
        seen["env"] = os.environ.get("ADBUTILS_ADB_PATH")
        return type("FakeDevice", (), {"info": {}})()

    monkeypatch.setattr(service.u2, "connect", fake_connect)
    service.Mobile().connect("emulator-5554")
    assert seen["env"] == exe


def test_failed_connect_clears_previous_device(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from android_mcp.mobile import service

    mobile = service.Mobile()
    mobile.device = object()
    monkeypatch.setenv("ANDROID_MCP_ADB_PATH", str(clean_env / "nope"))
    with pytest.raises(RuntimeError, match="ANDROID_MCP_ADB_PATH"):
        mobile.connect("emulator-5554")
    assert not mobile.is_connected
