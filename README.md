# android-mcp-beta

Clean-room reimplementation of [Android-MCP](https://github.com/CursorTouch/Android-MCP): an MCP
server that lets an AI agent operate an Android device over ADB.

It needs only `adb`. Nothing is installed on the device, and there is no dependency on
uiautomator2.

## Run

Requires Python 3.13 and `adb` (Android platform-tools).

```
uv run android-mcp-beta
```

The server speaks MCP on stdio. In a client's config:

```json
{
  "mcpServers": {
    "android-mcp-beta": {
      "command": "uv",
      "args": ["--directory", "D:/Projects/android-mcp-beta", "run", "android-mcp-beta"]
    }
  }
}
```

The device is connected on the first tool call, so the server starts whether or not one is
attached yet.

## Choosing the device

With no options it uses the first physical device, or an emulator when there is none.

| Option | Environment | Meaning |
|---|---|---|
| `--device SERIAL` | `ANDROID_MCP_DEVICE` | A serial, or `host:port` for a device on the network |
| `--connection auto\|usb\|wifi` (alias `--transport`) | `ANDROID_MCP_CONNECTION` | How to pick when no device is named |
| `--wifi [HOST]` | `ANDROID_MCP_HOST` | ADB over Wi-Fi; `HOST` or `HOST:PORT`, port 5555 by default |
| `--usb [SERIAL]` | | ADB over USB, optionally a specific serial |

Options win over the environment. Other variables:

- `ANDROID_MCP_ADB_PATH` names the `adb` binary. Otherwise `adb` is looked for on `PATH`, then in
  `ANDROID_HOME`, `ANDROID_SDK_ROOT` and the default Android Studio SDK folders.
- `SCREENSHOT_QUANTIZED=true` reduces screenshots to 256 colours, which makes them smaller.

## Tools

| Tool | Does |
|---|---|
| `ListDevices`, `ConnectDevice`, `Device` | List, choose, or disconnect the device |
| `Snapshot` | The interactive elements, each with a label and tap coordinates. `use_vision` adds a screenshot with the labels drawn on it; `use_annotation=false` leaves it clean |
| `Click`, `LongClick`, `Swipe`, `Drag` | Touch input by coordinates |
| `ClickBySelector` | Tap an element found by `text`, `resourceId`, `className` or `description` (exact match; `resourceId` may be the part after the slash), with `index` for the nth match |
| `Type` | Type into a field. `x` and `y` tap it first; `clear` empties it first. Other scripts and emoji need the optional ADBKeyboard app (below) |
| `Press` | A button: back, home, recent, volume up, enter, and so on |
| `Notification` | Pull down the notification shade |
| `Wait`, `WaitForElement` | Pause, or wait for an element to appear |

## Typing other scripts (optional)

`Type` uses `adb shell input text`, so on its own it types printable ASCII and the accented Latin
letters Android can compose (é ñ ü ÿ and 107 others, not ç ß å ø). A newline presses Enter and a
tab presses Tab. For anything else (CJK, Cyrillic, Arabic, emoji, ç), install the
[ADBKeyboard](https://github.com/senzhk/ADBKeyBoard) app on the device once:

```
adb install keyboardservice-debug.apk
```

Download it from the [releases page](https://github.com/senzhk/ADBKeyBoard/releases). This project
does not bundle it: ADBKeyboard is GPL-2.0, and it is only ever talked to over broadcasts. I tested
v2.5-dev (SHA-256 `41a8a099…46fbbb`) on Android 15.

With it installed, text that `input text` cannot type is sent through it automatically. For about
a second the device's keyboard is switched to ADBKeyboard, which shows no keyboard of its own, and
then the keyboard that was active before is put back (and ADBKeyboard is disabled again if it was
not enabled). A text field must be focused, or the call fails with an error saying so. If a crash
ever leaves the device on ADBKeyboard, `adb shell ime reset` restores the default. Without the app,
such text is rejected before anything is sent, with these instructions in the error.

## Other limits

- **Busy screens.** The element list comes from `uiautomator dump`, which gives up when the screen
  never goes idle (a video, a running timer). `Snapshot` with `use_vision` then returns the
  screenshot alone and says so; click by coordinates still works.
- **Drag** needs Android 8 or later. **Clearing a field** uses `input keycombination`, which needs
  Android 12; older devices fall back to a slower method that clears up to 200 characters.

## Development

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

The tests need no device. Layers, bottom to top: `android_mcp.adb` (talks to `adb`),
`android_mcp.tree` (reads the screen), `android_mcp.mobile` (one connected device: state and
actions), `android_mcp.server` (the MCP tools and the choice of device).
