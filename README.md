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

**Android-MCP** is a lightweight, open-source bridge between AI agents and Android devices. Running as an MCP server, it lets large-language-model agents perform real-world tasks such as **app navigation, UI interaction and automated QA testing** without relying on traditional computer-vision pipelines.

## ✨ Key Features

- **Native Android Integration**  
  Interact with UI elements via ADB and the Android Accessibility API: launch apps, tap, swipe, input text, and read view hierarchies.

- **Bring Your Own LLM (Vision Optional)**  
  Works with any language model—no fine-tuned CV model or OCR pipeline required.

- **Rich Toolset for Mobile Automation**  
  Pre-built tools for gestures, keystrokes, capture, device state.

- **Real-Time Interaction**  
  Typical latency between actions (e.g., two taps) ranges **2 – 5 s** depending on device specs and load.

### Supported Operating Systems

- Android 10+

## 🚀 Installation

### Prerequisites

- **Python 3.10+**
- **Android Studio**

### 🏁 Getting Started

1. **Clone the repository**

```shell
   git clone https://github.com/CursorTouch/Android-MCP.git
   cd Android-MCP
```

2. **Install dependencies**

```shell
   uv pip install -r pyproject.toml
```

3. **Connect to the MCP server**

   Add the following JSON (replace `{{PATH}}` placeholders) to your client config:

```json
   {
     "mcpServers": {
       "android-mcp": {
         "command": "{{PATH_TO_UV}}",
         "args": [
           "--directory",
           "{{PATH_TO_SRC}}/Android-MCP",
           "run",
           "server.py"
         ]
       }
     }
   }
```

For Claude Desktop, save as `%APPDATA%/Claude/claude_desktop_config.json`.

4. **Enable ADB & authorize your device**

```shell
   adb devices   # verify that your phone/tablet appears and is "authorized"
```

5. **Restart the Claude Desktop**

   Open your Claude Desktop, “Android-MCP” should now appear as an integration.

For troubleshooting tips (log locations, common ADB issues), see the [MCP docs](https://modelcontextprotocol.io/quickstart/server#android-mcp-integration-issues).

---

## 🛠️ MCP Tools

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

## ⚠️ Caution

Android-MCP can execute arbitrary UI actions on your mobile device. Use it in controlled environments (emulators, test devices) when running untrusted prompts or agents.

## 🪪 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING](CONTRIBUTING) for dev setup and PR guidelines.

Made with ❤️ by [Jeomon George](https://github.com/Jeomon)

## Citation

```bibtex
@misc{
  author       = {Jeomon George},
  title        = {Android-MCP},
  year         = {2025},
  publisher    = {GitHub},
  howpublished = {\url{https://github.com/YourOrg/Android-MCP}},
  note         = {Lightweight open-source bridge between LLM agents and Android},
}
```
