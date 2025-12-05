"""The Emby Modern component."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_API_KEY, CONF_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import EmbyDataUpdateCoordinator
from .emby_client import EmbyClient, CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

# TODO: Comment out platforms you haven't created files for yet!
PLATFORMS = [
      Platform.MEDIA_PLAYER,
      Platform.SENSOR,
      Platform.BUTTON,
      Platform.REMOTE,
      Platform.UPDATE,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
      """Set up the Emby Modern component."""
      hass.data.setdefault(DOMAIN, {})
      return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
      """Set up Emby Modern from a config entry."""
      session = async_get_clientsession(hass)

    # 1. Initialize Client
      client = EmbyClient(
         entry.data[CONF_HOST], 
        entry.data[CONF_PORT], 
        entry.data[CONF_API_KEY],
        entry.data[CONF_SSL], 
        hass.loop, 
        session
     
 
   # 2. Validate Connection (Raise NotReady if offline so HA retries)
    try:
        await client.validate_connection()
        exc(CannotConnect, TimeoutError) as err:
        raise ConfigEntryNotReady(f"Emby not ready: {err}") from err
except   epException as err:
        _LOGGER.error(f"Failed to connect: {err}")
        return False
 
   # 3. Setup Coordinator
    coordinator = EmbyDataUpdateCoordinator(hass, client, entry)
    
    # Fetch initial data so we don't start with empty sensors
    await coordinator.async_config_entry_first_refresh()
 
   # 4. Store references
    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
 
   # 5. Register the Main Device (The Server itself)
    # We grab the version from the coordinator data we just fetched
    server_version = coordinator.data.get("system_info", {}).get("Version", "Unknown")
    
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, 
        identifiers={(entry.domain, entry.entry_id)},
        manufacturer="Emby", 
        name=client.get_server_name(), 
        model="Emby Server", 
        sw_version=server_version,
        configuration_url=client.get_server_url(),
    )
 
   # 6. Load Platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True
a
sync def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
