# Security Policy

## What OpenProxy does with your traffic

OpenProxy is a man-in-the-middle debugging proxy. To decrypt HTTPS it generates a local root certificate authority (via mitmproxy) and asks you to trust it on your computer and test devices. A few things worth knowing:

- **The CA private key lives on your machine** in `~/.mitmproxy/` (`%USERPROFILE%\.mitmproxy\` on Windows). Anyone who obtains that key can impersonate any HTTPS site to devices that trust the certificate. Do not share it, and do not commit it to a repository.
- **Only trust the CA on devices you control**, and remove it from the device's trust store when you are done testing.
- **Traffic stays local.** OpenProxy does not send captured requests, responses, or certificates anywhere. The only outbound call the app makes on its own behalf is a version check against the GitHub Releases API on startup.
- **VPN Mode** starts a local WireGuard endpoint so a phone on your Wi-Fi can route through the proxy. Only enable it on networks you trust and turn it off afterwards.
- **System proxy toggles** (macOS `networksetup`, Windows/Linux OS proxy) route all of that machine's traffic through OpenProxy. Remember to turn them back off.

## Supported versions

Only the latest release on the [Releases page](https://github.com/TiagoParente32/open-proxy/releases/latest) is supported. The app checks for updates on startup; please update before reporting an issue.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Instead, use GitHub's private reporting: go to the repository's **Security** tab and click **Report a vulnerability**, or email **t.parente.32@gmail.com** with:

- A description of the issue and its impact
- Steps to reproduce, or a proof of concept
- The OpenProxy version and operating system you tested on

You should receive an acknowledgement within a few days. Once the issue is confirmed, a fix will be released as a new version and the advisory will be published after users have had a chance to update. Credit is given to reporters unless they prefer to stay anonymous.

## Scope

In scope:

- The OpenProxy desktop application (Electron shell, Vue UI, Python backend)
- The auto-update mechanism
- Build and release scripts in this repository

Out of scope:

- Vulnerabilities in upstream dependencies (mitmproxy, Electron, Vue, WireGuard). Please report those to the respective projects, but feel free to open an issue here so we can update the dependency.
- Issues that require the attacker to already have local admin/root access to the machine running OpenProxy.
