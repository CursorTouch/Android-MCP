<div align="center">

  <h1>🤖 Android MCP</h1>

  <a href="https://github.com/CursorTouch/Android-MCP/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python">
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

- Python 3.10+
- UIautomator2
- Android 10+ (Emulator/ Android Device)
- A computer to run MCP server

### 🏁 Getting Started

1. **Clone the repository**

```shell
   git clone https://github.com/CursorTouch/Android-MCP.git
   cd Android-MCP
```

2. **Install dependencies**

```shell
   uv python install 3.10
   uv sync
```

3. **Connect to the MCP server**

1. Locate your Claude Desktop configuration file:

  - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
  - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

2. Add the following JSON to your Claude Desktop config:

  ```json
    {
      "mcpServers": {
        "android-mcp": {
          "command": "path/to/uv",
          "args": [
            "--directory",
            "path/to/Android-MCP",
            "run",
            "main.py",
            "--emulator"
          ]
        }
      }
    }
  ```
  Replace:
  - `path/to/uv` with the actual path to your uv executable
  - `path/to/Android-MCP` with the absolute path to where you have cloned this repo

  NOTE: `--emulator` this is used to run in emulator, remove it to use actual device

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
