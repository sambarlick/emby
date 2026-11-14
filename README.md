# Emby (Modern) for Home Assistant

![Built with Gemini](https://img.shields.io/badge/Built%20with-Gemini-8E75B2?style=for-the-badge&logo=google-gemini&logoColor=white)
![Built with Claude](https://img.shields.io/badge/Built%20with-Claude-D97757?style=for-the-badge&logo=claude&logoColor=white)
[![Marketplace Custom](https://img.shields.io/badge/Marketplace-Custom-orange.svg?style=for-the-badge)](https://www.home-assistant.io/blog/2026/11/04/release-202611/)
[![GitHub Release](https://img.shields.io/github/release/sambarlick/emby.svg?style=for-the-badge&color=blue)](https://github.com/sambarlick/emby/releases)
[![Maintainer](https://img.shields.io/badge/maintainer-%40sambarlick-blue.svg?style=for-the-badge)](https://github.com/sambarlick)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sambarlick&repository=emby&category=integration)

---

A robust, modern integration for Emby Media Server, designed to replace the legacy built-in integration.

This integration focuses on stability, connection resilience and modern Home Assistant architecture, with live updates over Emby's WebSocket.

## ✨ Features

* **⚡ Discovery:** Finds your Emby server on the network automatically (SSDP).
* **📺 You choose the clients:** Pick which Emby apps and devices appear in Home Assistant. Selected clients stay put and show as Off when idle. When a new client connects, a Repairs notice offers to add it.
* **🎥 Media players:** Play, pause, seek, volume, artwork and progress, updated live.
* **📂 Media browser:** Browse your libraries from any Emby media player and send media to it.
* **🎬 Media sidebar:** Browse and play Emby libraries in Home Assistant's Media panel. Emby transcodes for the browser.
* **📊 Library sensors:** Item counts per library (series and episodes counted separately), with recently added items. They refresh when Emby reports a library change.
* **⬆️ Server updates:** The standard Home Assistant update entity shows new Emby Server releases. Install is offered on servers that can update themselves.
* **🔘 Server controls:** Restart and Scan Library buttons, plus Shutdown (disabled by default).
* **🔔 Shutdown Courtesy Mode:** Warns viewers with a pop-up before the server restarts or shuts down.
* **🔒 Re-authentication:** If Emby stops accepting the API key, Home Assistant asks for a new one.
* **🩺 Diagnostics:** Download a debug file with secrets removed.

## ⚠️ Known Limitations

* **Volume control** depends on the Emby app. Some apps can't change volume when audio goes to a soundbar or AV receiver, so the slider may move without changing the sound. Mute usually still works.
* **Media sidebar playback** needs your browser to reach the Emby server directly, and Emby transcodes the stream.
* **Server updates** can't be installed from Home Assistant on Linux service, Docker or LXC installs. Emby can't update itself there, so the update entity only shows the new version.
* **Stop button:** Home Assistant's media card doesn't show Stop for players that can pause. Use the power button to stop playback.

## 🗺️ Roadmap

* Paging in the media browser for very large libraries.
* Submission to the Home Assistant Marketplace's default catalogue.

## 📥 Installation

### Option 1: Marketplace (Recommended)
Home Assistant 2026.11 and later include the Marketplace (formerly HACS).

1.  Click the **Open your Home Assistant instance** button above, or go to **Settings** -> **Marketplace** -> **Add from link** and enter `https://github.com/sambarlick/emby`.
2.  Download **Emby (Modern)**.
3.  Restart Home Assistant.

Updates appear under **Settings** -> **Updates**. A restart is needed after updating.

On Home Assistant 2026.10 or earlier, add this repository as a custom repository in HACS (category: **Integration**) instead.

### Option 2: Manual
1.  Download the latest release zip.
2.  Extract the `emby_modern` folder.
3.  Place it in your `config/custom_components/` directory.
4.  Restart Home Assistant.

## ⚙️ Configuration

1.  Go to **Settings** -> **Devices & Services**.
2.  If your server is on the same network, it should be discovered automatically! Click **Configure**.
3.  If not discovered, click **Add Integration** and search for **Emby (Modern)**.
4.  Enter your Host (IP) and API Key.
5.  Tick the Emby clients you want as devices.

### Choosing Emby clients
Emby often creates a new client for each browser or app reinstall. To change which ones are in Home Assistant, go to **Settings** -> **Devices & Services** -> **Emby (Modern)** and click the **settings cog**. Unticking a client removes its device.

Remote and Stop Session entities are created for each client but disabled by default. Enable them on the device page if you use them.

### Shutdown Courtesy Mode
Turn on the **Shutdown Courtesy Mode** switch on the server device. When Emby is about to restart or shut down, every connected client that supports messages gets a pop-up warning viewers that playback will be interrupted. The switch remembers its setting across restarts.

To send your own messages, use the `emby_modern.send_message` action.

### Changing the server address
If your Emby server's IP address, port or API key changes, you don't need to remove the integration:

1.  Go to **Settings** -> **Devices & Services** -> **Emby (Modern)**.
2.  Open the **⋮** menu on the server entry and choose **Reconfigure**.
3.  Enter the new details. Leave the API Key blank to keep the current one.

Your devices, entities and automations are kept. The new address must point to the same Emby server; to switch to a different server, add it as a new integration.

## Credits
* **Architect & Maintainer:** @sambarlick
* **Code Generation:** Google Gemini (AI), Anthropic Claude (AI)
* **Inspiration:** The official Jellyfin Home Assistant integration architecture.
