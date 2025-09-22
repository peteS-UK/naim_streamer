from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries, core
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    RepeatMode,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers import (
    config_validation as cv,
    entity_platform,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SERVICE_SEND_COMMAND, CONF_BROADLINK, BROADLINK_COMMANDS

from .coordinator import StreamerDataUpdateCoordinator
from .entity import StreamerEntity


_LOGGER = logging.getLogger(__name__)

SUPPORT_STREAMER = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.REPEAT_SET
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
)

SOURCES = ("CD", "Radio", "PC", "iPod", "TV", "AV", "HDD", "Aux")


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: StreamerEntity,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Media Player"""

    async_add_entities(
        [NaimStreamerDevice(coordinator=config_entry.runtime_data.coordinator)]
    )


class NaimStreamerDevice(StreamerEntity, MediaPlayerEntity):
    # Representation of a Naim Streamer

    def __init__(self, coordinator: StreamerDataUpdateCoordinator):
        super().__init__(coordinator)
        self._streamer = coordinator.streamer
        self._state = MediaPlayerState.IDLE
        self._unique_id = self._streamer.udn
        self._device_class = "receiver"
        self._name = self._streamer.name
        self._source = ""
        self._sources = SOURCES
        self._shuffle = False
        self._attr_unique_id = coordinator.uuid
        self._attr_name = None
        self._attr_has_entity_name = True

    @property
    def should_poll(self):
        return False

    @property
    def icon(self):
        return "mdi:disc"

    @property
    def source_list(self):
        return self._sources

    @property
    def source(self):
        return self._source

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_class(self):
        return self._device_class

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        return SUPPORT_STREAMER

    @property
    def repeat(self):
        return RepeatMode.ONE

    @property
    def shuffle(self) -> bool:
        """Boolean if shuffle is enabled."""
        return self._shuffle

    @property
    def volume_level(self):
        volume = self.coordinator.data.get("volume")
        return volume / 100 if volume is not None else None

    @property
    def is_volume_muted(self):
        return self.coordinator.data.get("mute")

    @property
    def state(self):
        return self.coordinator.data.get("state")

    @property
    def media_title(self):
        return self.coordinator.data.get("media_title")

    @property
    def media_artist(self):
        return self.coordinator.data.get("media_artist")

    @property
    def media_duration(self):
        return self.coordinator.data.get("media_duration")

    async def async_media_play(self):
        """Send play command to the streamer."""
        await self.coordinator.streamer.play()
        self.coordinator.data["state"] = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    async def async_media_pause(self):
        """Send pause command to the streamer."""
        await self.coordinator.streamer.pause()
        self.coordinator.data["state"] = MediaPlayerState.PAUSED
        self.async_write_ha_state()

    async def async_media_stop(self):
        """Send stop command to the streamer."""
        await self.coordinator.streamer.stop()
        self.coordinator.data["state"] = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float):
        """
        Set volume level.
        volume: 0.0–1.0
        """
        vol_int = int(volume * 100)
        await self.coordinator.streamer.set_volume(vol_int)
        self.coordinator.data["volume"] = vol_int
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool):
        """Mute or unmute the volume, then confirm the actual state."""
        # UPnP expects "1" or "0" as DesiredMute
        _LOGGER.critical("Mute: %s", await self.coordinator.streamer.set_mute(mute))

        # Read back the mute state from the device
        mute_data = await self.coordinator.streamer.get_mute(parsed=True)
        # UPnP returns "0" or "1" as strings under CurrentMute
        actual_mute = bool(int(mute_data.get("CurrentMute", 0)))

        # Update coordinator snapshot with the confirmed value
        self.coordinator.data["mute"] = actual_mute

        # Push the update to HA immediately
        self.async_write_ha_state()

    async def async_media_next_track(self):
        await self.coordinator.streamer.next()
        self.coordinator.data["state"] = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    async def async_media_previous_track(self):
        await self.coordinator.streamer.previous()
        self.coordinator.data["state"] = MediaPlayerState.PLAYING
        self.async_write_ha_state()
