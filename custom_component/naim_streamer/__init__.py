from homeassistant import config_entries, core
from homeassistant.const import Platform

from .coordinator import StreamerDataUpdateCoordinator

# from . import StreamerData, StreamerConfigEntry

from .const import DOMAIN

import logging


from dataclasses import dataclass
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [Platform.MEDIA_PLAYER]


@dataclass
class StreamerData:
    """Streamer data class."""

    coordinator: StreamerDataUpdateCoordinator


type StreamerConfigEntry = ConfigEntry[StreamerData]


async def async_setup_entry(
    hass: core.HomeAssistant, config_entry: StreamerConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""

    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(config_entry.data)
    hass.data[DOMAIN][config_entry.entry_id] = hass_data

    coordinator = StreamerDataUpdateCoordinator(hass, config_entry)

    config_entry.runtime_data = StreamerData(coordinator=coordinator)
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok
