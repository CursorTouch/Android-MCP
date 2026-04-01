# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Android-MCP, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please report security issues by:

1. Opening a [GitHub Security Advisory](https://github.com/CursorTouch/Android-MCP/security/advisories/new) in this repository.
2. Or emailing the maintainers directly (see the repository profile for contact details).

Please include:
- A description of the vulnerability and its potential impact.
- Steps to reproduce the issue.
- Any suggested mitigations or fixes (optional but appreciated).

We aim to respond to security reports within **72 hours** and will work with you to understand and address the issue promptly.

## Security Considerations

Android-MCP communicates with Android devices over ADB. Please ensure:
- ADB is only exposed on trusted networks.
- Devices used with this tool are not connected to untrusted or public networks.
- Credentials and sensitive data are never passed as plain-text tool arguments in production environments.
