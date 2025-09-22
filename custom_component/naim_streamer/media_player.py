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
)

SOURCES = ("CD", "Radio", "PC", "iPod", "TV", "AV", "HDD", "Aux")


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: StreamerEntity,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Media Player"""

    async_add_entities(
        [
            NaimStreamerDevice(
                coordinator=config_entry.runtime_data.coordinator, hass=hass
            )
        ]
    )


class NaimStreamerDevice(StreamerEntity, MediaPlayerEntity):
    # Representation of a Naim Streamer

    def __init__(
        self, coordinator: StreamerDataUpdateCoordinator, hass: core.HomeAssistant
    ):
        self._streamer = coordinator.streamer
        self._hass = hass
        self._state = MediaPlayerState.IDLE
        self._unique_id = self._streamer.udn
        self._device_class = "receiver"
        self._name = self._streamer.name
        self._source = ""
        self._sources = SOURCES
        self._shuffle = False

    @property
    def should_poll(self):
        return False

    @property
    def icon(self):
        return "mdi:disc"

    @property
    def state(self) -> MediaPlayerState:
        return self._state

    @property
    def name(self):
        return None

    @property
    def has_entity_name(self):
        return True

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
