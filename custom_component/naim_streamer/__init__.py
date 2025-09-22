from .naim_streamer_client import NaimStreamerClient

from homeassistant import config_entries, core
from homeassistant.const import Platform

from .const import (
    DOMAIN,
)

import logging


_LOGGER = logging.getLogger(__name__)


PLATFORMS = [Platform.MEDIA_PLAYER]


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""

    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(entry.data)
    hass.data[DOMAIN][entry.entry_id] = hass_data

    client = NaimStreamerClient(
        name=hass_data["name"],
        udn=hass_data["udn"],
        manufacturer=hass_data["manufacturer"],
        model=hass_data["model"],
        port=hass_data["port"],
        rendering_control_url=hass_data["rendering_control_url"],
        av_transport_url=hass_data["av_transport_url"],
        connection_manager_url=hass_data["connection_manager_url"],
    )

    hass_data[DOMAIN] = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok
