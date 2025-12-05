# Emby (Modern) for Home Assistant

A robust, modern integration for Emby Media Server, designed to replace the legacy built-in integration.

This integration focuses on stability, connection resilience, and using modern Home Assistant architecture (DataUpdateCoordinators) to ensure your entities state stays in sync with your server.

## ✨ Features

* **⚡ ZeroConf Discovery:** Automatically finds your Emby server on the network—no manual IP entry required.
* **🚀 Data Update Coordinator:** Uses efficient polling to keep server availability and library status in sync without overloading Home Assistant.
* **🔒 Authentication:** Proper handling of Emby API Keys and User Sessions.
* **🎥 Media Players:** Controls for all your Emby sessions.
* **📊 Library Statistics:** Real-time sensors for Movie, Series, and Episode counts.  <-- MOVED HERE
* **🎮 Remote Control:** Control your Emby clients directly.
* **🔘 Buttons:** Trigger server tasks instantly.
* **🛠️ Robustness:** Handles server restarts and connection drops gracefully.

## ⚠️ Known Limitations & Roadmap

* **Active Platforms:** Media Player, Sensor, Button, Remote.
* **Future Plans:**
    * Re-introduce Browse Media (v2.0).

## 📥 Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sambarlick&repository=emby&category=integration)

### Option 1: HACS (Recommended)
1.  Open HACS in Home Assistant.
2.  Click the **3 dots** in the top right -> **Custom repositories**.
3.  Add the URL of this repository.
4.  Category: **Integration**.
5.  Click **Download**.
6.  Restart Home Assistant.

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

## Credits
Built by **@sambarlick**.
Inspired by the Jellyfin core integration architecture.
