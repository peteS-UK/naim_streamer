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
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    RepeatMode,
)

TRANSPORT_TO_HA_STATE = {
    "STOPPED": MediaPlayerState.IDLE,
    "NO_MEDIA_PRESENT": MediaPlayerState.IDLE,
    "PLAYING": MediaPlayerState.PLAYING,
    "PAUSED_PLAYBACK": MediaPlayerState.PAUSED,
    "TRANSITIONING": MediaPlayerState.PLAYING,  # treat as active
}


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
            update_interval=timedelta(seconds=10),
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

        await self._async_update_data()

    async def _async_update_data(self):
        """Fetch the latest state from the Naim streamer."""
        try:
            # Volume
            vol_data = await self.streamer.get_volume(parsed=True)
            volume = int(vol_data.get("CurrentVolume", 0))

            # Mute
            mute_data = await self.streamer.get_mute(parsed=True)
            mute = bool(int(mute_data.get("CurrentMute", 0)))

            # Transport state (map to HA MediaPlayerState)
            transport_data = await self.streamer.get_transport_info(parsed=True)
            raw_transport_state = str(
                transport_data.get("CurrentTransportState", "UNKNOWN")
            )
            ha_state = TRANSPORT_TO_HA_STATE.get(
                raw_transport_state.upper(), MediaPlayerState.IDLE
            )

            # Media info
            media_info = await self.streamer.get_media_info(parsed=True)
            media_title = media_info.get("Title", "")
            media_artist = media_info.get("Artist", "")
            raw_duration = media_info.get("MediaDuration", "0")
            if ":" in raw_duration:
                try:
                    h, m, s = (int(x) for x in raw_duration.split(":"))
                    media_duration = h * 3600 + m * 60 + s
                except ValueError:
                    media_duration = 0
            else:
                media_duration = int(raw_duration) if raw_duration.isdigit() else 0

            return {
                "volume": volume,
                "mute": mute,
                "state": ha_state,  # already mapped to HA enum
                "media_title": media_title,
                "media_artist": media_artist,
                "media_duration": media_duration,
            }

        except Exception as err:
            raise UpdateFailed(f"Error fetching data from streamer: {err}") from err
