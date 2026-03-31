<div align="center">

  <h1>🤖 Android MCP</h1>

  <a href="https://github.com/CursorTouch/Android-MCP/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.13-blue" alt="Python">
  <img src="https://img.shields.io/badge/platform-Android%2010+-blue" alt="Platform">
  <img src="https://img.shields.io/github/last-commit/CursorTouch/Android-MCP" alt="Last Commit">
  <br>
  <a href="https://x.com/CursorTouch">
    <img src="https://img.shields.io/badge/follow-%40CursorTouch-1DA1F2?logo=twitter&style=flat" alt="Follow on Twitter">
  </a>
  <a href="https://discord.com/invite/Aue9Yj2VzS">
    <img src="https://img.shields.io/badge/Join%20on-Discord-5865F2?logo=discord&logoColor=white&style=flat" alt="Join us on Discord">
  </a>

</div>

<br>

**Android-MCP** is a lightweight, open-source tool that bridge between AI agents and Android devices. Running as an MCP server, it lets LLM agents perform real-world tasks such as **app navigation, UI interaction and automated QA testing** without relying on traditional computer-vision pipelines or preprogramed scripts.

<https://github.com/user-attachments/assets/cf9a5e4e-b69f-46d4-8487-0f61a7a86d67>

## ✨ Features

- **Native Android Integration**  
  Interact with UI elements via ADB and the Android Accessibility API: launch apps, tap, swipe, input text, and read view hierarchies.

- **Bring Your Own LLM/VLM**  
  Works with any language model, no fine-tuned CV model or OCR pipeline required.

- **Rich Toolset for Mobile Automation**  
  Pre-built tools for gestures, keystrokes, capture, device state, shell commands execution.

- **Real-Time Interaction**  
  Typical latency between actions (e.g., two taps) ranges **2-4s** depending on device specs and load.

### Supported Operating Systems

- Android 10+

## Installation

### 📦 Prerequisites

- Python 3.13
- ADB (Android Debug Bridge)
- Android 10+ (Emulator/ Android Device)

### 📲 Testing ADB Connection

Before running the server, ensure your Android device is connected and recognized by ADB:

1. Connect your Android device via USB or ensure your emulator is running.
2. Open a terminal and run:
   ```shell
   adb devices
   ```
3. You should see your device listed:
   ```
   List of devices attached
   emulator-5554   device
   ```
   If the list is empty or shows "unauthorized", check your USB debugging settings on the device.

For WiFi ADB, connect the device first:

```shell
adb connect 192.168.1.3:5555
adb devices
```

### 🏁 Getting Started

You can run the Android MCP server using **UVX** (recommended) or **UV** (for local development).

#### Option 1: UVX (Recommended)

No need to install dependencies manually. Just configure Claude Desktop:

> **Windows note:** Use Python 3.13 for `uvx` on Windows. Python 3.14 currently fails to resolve a transitive `pywin32` dependency used by the MCP stack.

1. **Locate your config file**
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

2. **Add the configuration**
   ```json
   {
     "mcpServers": {
       "android-mcp": {
         "command": "uvx",
         "args": [
           "--python",
           "3.13",
           "android-mcp"
         ]
       }
     }
   }
   ```
   > **Note:** The server starts first and connects lazily when a tool runs. If no device is specified, it auto-detects the first available ADB device instead of hardcoding `emulator-5554`.

   Configure a specific WiFi device with environment variables:

   ```json
   {
     "mcpServers": {
       "android-mcp": {
         "command": "uvx",
         "args": [
           "--python",
           "3.13",
           "android-mcp"
         ],
         "env": {
           "ANDROID_MCP_CONNECTION": "wifi",
           "ANDROID_MCP_HOST": "192.168.1.3"
         }
       }
     }
   }
   ```

   Or pass explicit flags:

   ```json
   {
     "mcpServers": {
       "android-mcp": {
         "command": "uvx",
         "args": [
           "--python",
           "3.13",
           "android-mcp",
           "--wifi",
           "192.168.1.3"
         ]
       }
     }
   }
   ```

#### Option 2: UV Mode (Local Development)

1. **Clone and Install**
   ```shell
   git clone https://github.com/CursorTouch/Android-MCP.git
   cd Android-MCP
   uv sync
   ```

2. **Configure Claude Desktop**
   ```json
   {
     "mcpServers": {
       "android-mcp": {
         "command": "uv",
         "args": [
           "--directory",
           "</PATH/TO/Android-MCP>",
           "run",
           "android-mcp"
         ]
       }
     }
   }
   ```
   > **Note:** Replace `</PATH/TO/Android-MCP>` with the full path to your cloned directory. You can also add `"--device", "<YOUR_DEVICE_serial>"`, `"--wifi", "192.168.1.3"`, or `"--usb"` to control device selection.
   > `uv sync` follows the repo's `.python-version`, so local development uses Python 3.13 by default.

### 🔌 Device Selection

Android-MCP resolves devices lazily when a tool is called, so the MCP server can start even if no device is available yet.

- `--device RFCN2013V8D`: connect to a specific USB serial
- `--device 192.168.1.3:5555`: connect to a specific WiFi ADB target
- `--wifi 192.168.1.3`: use WiFi and auto-append port `5555`
- `--usb`: auto-detect the first USB-connected device
- `--usb RFCN2013V8D`: use a specific USB device
- `--connection wifi`: prefer the first available WiFi ADB device
- `--connection usb`: prefer the first available USB device

Supported environment variables:

- `ANDROID_MCP_DEVICE`: explicit serial or `host:port`
- `ANDROID_MCP_CONNECTION`: `auto`, `usb`, or `wifi`
- `ANDROID_MCP_HOST`: WiFi host, with `:5555` added automatically when omitted

If nothing is configured, Android-MCP will use the first available ADB device reported by `adb devices`. If none are available, tool calls return a configuration error instead of crashing the MCP handshake.

3. **Restart the Claude Desktop**

Restart your Claude Desktop. You should see "android-mcp" listed as an available integration. That's it, now you're ready to start controlling your Android device with natural language.

For troubleshooting tips (log locations, common ADB issues), see the [MCP docs](https://modelcontextprotocol.io/quickstart/server#android-mcp-integration-issues).

---

## 🛠️ Available Tools

Claude can access the following tools to interact with Windows:

- `State-Tool`: To understand the state of the device.
- `Click-Tool`: Click on the screen at the given coordinates.
- `Long-Click-Tool`: Perform long click on the screen at the given coordinates.
- `Type-Tool`: Type text on the specified coordinates (optionally clears existing text).
- `Swipe-Tool`: Perform swipe from one location to other.
- `Drag-Tool`: Drag from one point to another.
- `Press-Tool`: To press the keys on the mobile device (Back, Volume Up, ...etc).
- `Wait-Tool`: Pause for a defined duration.
- `State-Tool`: Combined snapshot of active apps and interactive UI elements.
- `Notification-Tool`: To access the notifications seen on the device.
- `Shell-Tool`: To execute shell commands on the android device.

## ⚙️ Environment Variables

- `SCREENSHOT_QUANTIZED`: Set to `true` to quantize the screenshot to reduce input tokens.

## ⚠️ Caution

Android-MCP can execute arbitrary UI actions on your mobile device. Use it in controlled environments (emulators, test devices) when running untrusted prompts or agents.

## 🪪 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING](CONTRIBUTING) for dev setup and PR guidelines.

Made with ❤️ by [CursorTouch](https://github.com/cursortouch), 

developers: [Jeomon George](https://github.com/jeomon), [Muhammad Yaseen](https://github.com/mhmdyaseen)

## Citation

```bibtex
@misc{
  author       = {cursortouch},
  title        = {Android-MCP},
  year         = {2025},
  publisher    = {GitHub},
  howpublished = {\url{https://github.com/CursorTouch/Android-MCP}},
  note         = {Lightweight open-source bridge between LLM agents and Android},
}
```
