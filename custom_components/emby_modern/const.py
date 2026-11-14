"""Constants for the Emby Modern integration."""
from datetime import timedelta

from homeassistant.components.media_player import MediaClass, MediaType

DOMAIN = "emby_modern"

# Options
CONF_CLIENTS = "clients"  # list of Emby DeviceIds the user selected

# Polling
SESSION_SCAN_INTERVAL = timedelta(seconds=10)
LIBRARY_SCAN_INTERVAL = timedelta(hours=1)
UPDATE_CHECK_INTERVAL = timedelta(hours=6)
LIBRARY_CHANGE_DEBOUNCE = 30  # seconds

EMBY_RELEASES_URL = "https://api.github.com/repos/MediaBrowser/Emby.Releases/releases"

# Item types counted per library CollectionType. The first type is the sensor
# value; any others are exposed as attributes.
LIBRARY_COUNT_TYPES: dict[str | None, list[str]] = {
    "movies": ["Movie"],
    "tvshows": ["Series", "Episode"],
    "music": ["MusicAlbum", "Audio"],
    "musicvideos": ["MusicVideo"],
    "homevideos": ["Video", "Photo"],
    "photos": ["Photo"],
    "books": ["Book"],
    "audiobooks": ["AudioBook"],
    "boxsets": ["BoxSet"],
    "playlists": ["Playlist"],
}
DEFAULT_COUNT_TYPES = ["Movie", "Series", "Video", "MusicVideo", "Audio", "Photo", "Book", "AudioBook"]

# Media browsing
CONTENT_TYPE_MAP = {
    "Movie": MediaType.MOVIE,
    "Episode": MediaType.EPISODE,
    "Series": MediaType.TVSHOW,
    "Season": MediaType.SEASON,
    "MusicAlbum": MediaType.ALBUM,
    "Audio": MediaType.TRACK,
    "Video": MediaType.VIDEO,
    "MusicVideo": MediaType.VIDEO,
    "TvChannel": MediaType.CHANNEL,
    "Folder": "library",
    "CollectionFolder": "library",
    "UserView": "library",
    "BoxSet": "library",
    "Playlist": MediaType.PLAYLIST,
}

MEDIA_CLASS_MAP = {
    "Movie": MediaClass.MOVIE,
    "Episode": MediaClass.EPISODE,
    "Series": MediaClass.TV_SHOW,
    "Season": MediaClass.SEASON,
    "MusicAlbum": MediaClass.ALBUM,
    "Audio": MediaClass.TRACK,
    "Video": MediaClass.VIDEO,
    "MusicVideo": MediaClass.VIDEO,
    "Folder": MediaClass.DIRECTORY,
    "CollectionFolder": MediaClass.DIRECTORY,
    "UserView": MediaClass.DIRECTORY,
    "TvChannel": MediaClass.CHANNEL,
    "BoxSet": MediaClass.DIRECTORY,
    "Playlist": MediaClass.PLAYLIST,
}

PLAYABLE_TYPES = {"Movie", "Episode", "Audio", "Video", "MusicVideo", "TvChannel"}
EXPANDABLE_TYPES = {"Series", "Season", "MusicAlbum", "BoxSet", "CollectionFolder", "UserView", "Folder", "Playlist"}
