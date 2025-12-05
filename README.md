# Emby Modern for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/sambarlick/emby.svg)](https://github.com/sambarlick/emby/releases)
[![License](https://img.shields.io/github/license/sambarlick/emby.svg)](LICENSE)

A modern, robust, and local-first integration for Emby Media Server in Home Assistant. 

**Emby Modern** is designed to replace the legacy built-in integration with a focus on stability, correct device identification, and deep media browsing support.

## ✨ Features

* **⚡ Local Push Updates:** Instant state updates via local polling and efficient API management.
* **🎬 Deep Media Browsing:** Browse your entire Emby library (Movies, TV, Music, Live TV) directly from the Home Assistant Media Browser.
* **🆔 Correct Device Identification:** Uses permanent System GUIDs instead of mutable server names, ensuring entities never break if you rename your server.
* **📺 Smart Media Player:** * Dynamically detects client types (TV, Tablet, Mobile, Web).
    * Supports "Play on" commands.
    * Displays accurate "Now Playing" info including Season/Episode details.
* **🎮 Remote Control:** Full remote control support (Up, Down, Select, Back, Home) for compatible Emby clients.
* **📊 Comprehensive Sensors:**
    * **Library Counts:** Track movie, episode, and song counts per library.
    * **Active Streams:** See who is watching what in real-time.
    * **Latest Media:** "Upcoming Media" attributes for dashboard cards.
* **🛠️ Admin Controls:** Restart server and trigger library scans directly from HA.

## 🚀 Installation

### Option 1: HACS (Recommended)
1.  Open HACS in Home Assistant.
2.  Go to **Integrations** > **Triple Dots (top right)** > **Custom Repositories**.
3.  Add the URL of this repository.
4.  Select **Integration** as the category.
5.  Click **Add** and then install **Emby Modern**.
6.  Restart Home Assistant.

### Option 2: Manual
1.  Download the `emby_modern` folder from this repository.
2.  Copy the folder into your Home Assistant's `custom_components/` directory.
3.  Restart Home Assistant.

## ⚙️ Configuration

1.  Go to **Settings** > **Devices & Services**.
2.  Click **+ Add Integration**.
3.  Search for **Emby Modern**.
4.  Enter your Emby Server details:
    * **Host:** IP address or hostname (e.g., `192.168.1.50`).
    * **Port:** Default is `8096` (HTTP) or `8920` (HTTPS).
    * **API Key:** Generate this in your Emby Dashboard under *Advanced > API Keys*.

> **Note:** Auto-discovery works if "Enable DLNA" is turned on in your Emby Server settings.

## 🖥️ Usage

### Media Browser
Click the "Media" icon in your Home Assistant sidebar. Select "Emby Modern" to browse your libraries. You can click any item to play it on a supported media player.

### Lovelace Card Example
```yaml
type: media-control
entity: media_player.
living_room_tv
