# Emby (Modern) for Home Assistant

![Built with Gemini](https://img.shields.io/badge/Built%20with-Gemini-8E75B2?style=for-the-badge&logo=google-gemini&logoColor=white)
![Built with Claude](https://img.shields.io/badge/Built%20with-Claude-D97757?style=for-the-badge&logo=claude&logoColor=white)
[![Marketplace Custom](https://img.shields.io/badge/Marketplace-Custom-orange.svg?style=for-the-badge)](https://www.home-assistant.io/blog/2026/11/04/release-202611/)
[![GitHub Release](https://img.shields.io/github/release/sambarlick/emby.svg?style=for-the-badge&color=blue)](https://github.com/sambarlick/emby/releases)
[![Maintainer](https://img.shields.io/badge/maintainer-%40sambarlick-blue.svg?style=for-the-badge)](https://github.com/sambarlick)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sambarlick&repository=emby&category=integration)

---

A robust, modern integration for Emby Media Server, designed to replace the legacy built-in integration.

This integration focuses on stability, connection resilience, and using modern Home Assistant architecture (DataUpdateCoordinators) to ensure your entities state stays in sync with your server.

## ✨ Features

* **⚡ ZeroConf Discovery:** Automatically finds your Emby server on the network—no manual IP entry required.
* **🚀 Data Update Coordinator:** Uses efficient polling to keep server availability and library status in sync without overloading Home Assistant.
* **🔒 Authentication:** Proper handling of Emby API Keys and User Sessions.
* **🎥 Media Players:** Controls for all your Emby sessions with artwork support.
* **📊 Library Statistics:** Real-time sensors for Movie, Series, and Episode counts.
* **🔘 Server Controls:** Dedicated buttons to **Restart Server** and **Scan Library** directly from Home Assistant.
* **🎮 Remote Control:** Control your Emby clients directly.
* **🔘 Buttons:** Trigger server tasks instantly.
* **🛠️ Robustness:** Handles server restarts and connection drops gracefully.

## ⚠️ Known Limitations & Roadmap

* **Latency:** This integration uses local polling. State updates (Play/Pause) may take a few seconds to reflect in Home Assistant.
* **Active Platforms:** Media Player, Sensor, Button, Remote.
* **Future Plans:**
    * Re-introduce Browse Media (v2.0).
    * WebSocket implementation for instant updates (v2.0).

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
