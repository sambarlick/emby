"""The Emby Modern component."""
import logging
import asyncio # New import for service delay

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_API_KEY, CONF_SSL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_set_service_schema # New import

from .const import DOMAIN
from .coordinator import EmbyDataUpdateCoordinator
from .emby_client import EmbyClient, CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.REMOTE,
    Platform.UPDATE,
    Platform.SWITCH, # ADDED: New switch platform
]

# ... async_setup remains unchanged ...

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
    )

    # 2. Validate Connection
    try:
        await client.validate_connection()
    except (CannotConnect, TimeoutError) as err:
        raise ConfigEntryNotReady(f"Emby not ready: {err}") from err
    except InvalidAuth as err:
        _LOGGER.error(f"Authentication failed: {err}")
        return False
    except Exception as err:
        _LOGGER.error(f"Unexpected error connecting to Emby: {err}")
        return False

    # 3. Setup Coordinator
    coordinator = EmbyDataUpdateCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    # 4. Store references
    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # 5. Register the Main Device (The Server itself)
    # ... (remains unchanged) ...
    server_version = coordinator.data.get("system_info", {}).get("Version", "Unknown")
    server_name = client.get_server_name() or "Emby Server"

    device_identifier = entry.unique_id or entry.entry_id

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_identifier)},
        manufacturer="Emby",
        name=server_name,
        model="Emby Server",
        sw_version=server_version,
        configuration_url=client.get_server_url(),
    )
    
    # 6. SETUP SERVICES AND LISTENERS (NEW BLOCK)
    
    # Service to send a custom message (used by automation, or the courtesy listener below)
    async def send_message_service(call):
        message = call.data.get("message")
        header = call.data.get("header", "Home Assistant Alert")
        timeout = call.data.get("timeout_ms", 5000)
        
        # Target all sessions
        sessions = coordinator.data.get("sessions", [])
        
        params = {
            "Header": header,
            "Text": message,
            "TimeoutMs": timeout
        }

        for session in sessions:
            try:
                 # Send message to all sessions
                await client.api_request("POST", f"Sessions/{session['Id']}/Message", params=params)
            except Exception as e:
                _LOGGER.warning(f"Failed to send message to session {session.get('UserName')}: {e}")

    hass.services.async_register(DOMAIN, "send_message", send_message_service)
    
    # Define the Courtesy Listener Logic
    @callback
    def _handle_courtesy_message(data):
        """Called when ServerShuttingDown or ServerRestarting event is received."""
        
        # 1. Check the state of the courtesy switch
        switch_entity_id = f"switch.emby_server_{entry.entry_id}_shutdown_courtesy_mode"
        switch_state = hass.states.get(switch_entity_id)

        if switch_state and switch_state.state == 'on':
            event_type = "Restarting" if data.get("EventName") == "ServerRestarting" else "Shutting Down"
            
            # Send the broadcast message asynchronously
            hass.async_create_task(
                send_message_service(
                    # Mimic the call object for the service
                    type('obj', (object,), {
                        'data': {
                            'message': f"System Alert: Emby Server is {event_type}. Services will be interrupted shortly.",
                            'header': "SYSTEM SHUTDOWN ALERT",
                            'timeout_ms': 10000
                        }
                    })
                )
            )

    # Register the Courtesy Listeners on the EmbyClient WebSocket
    client.add_message_listener("ServerShuttingDown", _handle_courtesy_message)
    client.add_message_listener("ServerRestarting", _handle_courtesy_message)
    
    # 7. Load Platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

# ... async_unload_entry and async_remove_config_entry_device remain unchanged ...
