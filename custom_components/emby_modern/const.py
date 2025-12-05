"""Constants for the Emby Modern integration."""
from homeassistant.components.media_player import MediaClass, MediaType

DOMAIN = "emby_modern"
CONF_CLIENT_DEVICE_ID = "client_device_id"

# Needed for browse_media.py to skip ignored devices
IGNORED_CLIENTS = [] 

# Needed for browse_media.py logic
MEDIA_TYPE_NONE = "none"

CONTENT_TYPE_MAP = {
    "Movie": MediaType.MOVIE,
    "Episode": MediaType.EPISODE,
    "Series": MediaType.TVSHOW,
    "Season": MediaType.SEASON,
    "MusicAlbum": MediaType.ALBUM,
    "Audio": MediaType.TRACK,
    "Video": MediaType.VIDEO,
    "TvChannel": MediaType.CHANNEL,
    "Folder": "library",            # Critical for browsing
    "CollectionFolder": "library",  # Critical for browsing
    "UserView": "library",          # Critical for browsing
    "BoxSet": "library",
}

MEDIA_CLASS_MAP = {
    "Movie": MediaClass.MOVIE,
    "Episode": MediaClass.EPISODE,
    "Series": MediaClass.TV_SHOW,
    "Season": MediaClass.SEASON,
    "MusicAlbum": MediaClass.ALBUM,
    "Audio": MediaClass.TRACK,
    "Folder": MediaClass.DIRECTORY,
    "CollectionFolder": MediaClass.DIRECTORY,
    "UserView": MediaClass.DIRECTORY,
    "TvChannel": MediaClass.CHANNEL,
    "BoxSet": MediaClass.DIRECTORY,
}

SUPPORTED_COLLECTION_TYPES = ["movies", "tvshows", "music", "musicvideos", "homevideos", "livetv"]
