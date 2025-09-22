"""DataUpdateCoordinator for the Squeezebox integration."""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING, Any

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .naim_streamer_client import NaimStreamerClient


@dataclass
class StreamerData:
    """Streamer data class."""

    coordinator: StreamerDataUpdateCoordinator


type StreamerConfigEntry = ConfigEntry[StreamerData]

DEFAULT_TIMEOUT = 10


_LOGGER = logging.getLogger(__name__)


class StreamerDataUpdateCoordinator(DataUpdateCoordinator):
    """Streamer custom coordinator."""

    config_entry: StreamerConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: StreamerConfigEntry,
    ) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=config_entry.data[CONF_NAME],
            update_interval=timedelta(seconds=30),
            always_update=False,
        )
        self.hass = hass
        self.config_entry = config_entry

    async def _async_setup(self):
        """Set up the coordinator

        This is the place to set up your coordinator,
        or to load data, that only needs to be loaded once.

        This method will be called automatically during
        coordinator.async_config_entry_first_refresh.
        """

        self.streamer = NaimStreamerClient(
            name=self.config_entry.data["name"],
            udn=self.config_entry.data["udn"],
            manufacturer=self.config_entry.data["manufacturer"],
            model=self.config_entry.data["model"],
            port=self.config_entry.data["port"],
            rendering_control_url=self.config_entry.data["rendering_control_url"],
            av_transport_url=self.config_entry.data["av_transport_url"],
            connection_manager_url=self.config_entry.data["connection_manager_url"],
        )
        self.uuid = self.streamer.udn

    async def _async_update_data(self):
        """Fetch data from API endpoint."""

        data: dict = {}
