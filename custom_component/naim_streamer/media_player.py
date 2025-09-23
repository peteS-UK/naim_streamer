from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import core
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.helpers import (
    config_validation as cv,
    entity_platform,
)

from homeassistant.exceptions import ServiceValidationError

from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    SERVICE_SEND_COMMAND,
    BROADLINK_COMMANDS,
    SOURCES,
)

from .coordinator import StreamerDataUpdateCoordinator
from .entity import StreamerEntity

TRANSPORT_TO_HA_STATE = {
    "STOPPED": MediaPlayerState.IDLE,
    "NO_MEDIA_PRESENT": MediaPlayerState.IDLE,
    "PLAYING": MediaPlayerState.PLAYING,
    "PAUSED_PLAYBACK": MediaPlayerState.PAUSED,
    "TRANSITIONING": MediaPlayerState.PLAYING,
}

_LOGGER = logging.getLogger(__name__)

SUPPORT_STREAMER = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SEEK
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: StreamerEntity,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Media Player"""

    async_add_entities(
        [NaimStreamerDevice(coordinator=config_entry.runtime_data.coordinator)]
    )

    # Register entity services
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SEND_COMMAND,
        {
            vol.Required("command"): cv.string,
        },
        NaimStreamerDevice.send_command.__name__,
    )


class NaimStreamerDevice(StreamerEntity, MediaPlayerEntity):
    # Representation of a Naim Streamer

    def __init__(self, coordinator: StreamerDataUpdateCoordinator):
        super().__init__(coordinator)
        self._streamer = coordinator.streamer
        self._unique_id = self._streamer.udn
        self._device_class = "receiver"
        self._name = self._streamer.name
        self._source = ""
        self._sources = SOURCES
        self._attr_unique_id = coordinator.uuid
        self._attr_name = None
        self._attr_has_entity_name = True
        self._broadlink_entity = coordinator.broadlink_entity

    @property
    def should_poll(self):
        return False

    async def send_command(self, command):
        if command == "play":
            await self.async_media_play
        elif command == "pause":
            await self.async_media_pause
        elif command == "stop":
            await self.async_media_stop
        elif command == "next":
            await self.async_media_next_track
        elif command == "previous":
            await self.async_media_previous_track
        elif command == "mute":
            await self.async_mute_volume(True)
        elif command == "unmute":
            await self.async_mute_volume(False)
        elif self._broadlink_entity:
            await self._send_broadlink_command(command)
        else:
            raise ServiceValidationError(
                f"{command} is only supported with a Broadlink remote"
            )

    async def _send_broadlink_command(self, command):
        await self._hass.services.async_call(
            "remote",
            "send_command",
            {
                "entity_id": self._broadlink_entity,
                "num_repeats": "1",
                "delay_secs": "0.4",
                "command": f"b64:{BROADLINK_COMMANDS[command]}",
            },
        )

    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        attrs = {}

        # Use streamer’s persistent values so they survive NOTIFY overwrites
        if self.coordinator.data.get("media_uri") or self._streamer.last_uri:
            attrs["current_uri"] = (
                self.coordinator.data.get("media_uri") or self._streamer.last_uri
            )
        if self.coordinator.data.get("media_metadata") or self._streamer.last_metadata:
            attrs["current_metadata"] = (
                self.coordinator.data.get("media_metadata")
                or self._streamer.last_metadata
            )

        return attrs

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
    def volume_level(self):
        volume = self.coordinator.data.get("volume")
        return volume / 100 if volume is not None else None

    @property
    def is_volume_muted(self):
        return self.coordinator.data.get("mute")

    @property
    def state(self):
        return self.coordinator.data.get("state")

    async def async_media_play(self):
        if self._broadlink_entity:
            await self._send_broadlink_command("play")
        else:
            if not self._streamer.last_uri or self._streamer.status == "ERROR_OCCURRED":
                uri = self.coordinator.data.get("media_uri") or self._streamer.last_uri
                metadata = (
                    self.coordinator.data.get("media_metadata")
                    or self._streamer.last_metadata
                )

                if uri and metadata:
                    _LOGGER.debug("Restoring AVTransport URI before play: %s", uri)
                    await self._streamer.set_av_transport_uri(uri, metadata)
                else:
                    _LOGGER.warning("No stored URI/metadata to restore before play")

            await self._streamer.play()

    async def async_media_pause(self):
        """Pause and confirm."""
        if self._broadlink_entity:
            await self._send_broadlink_command("pause")
        else:
            await self._streamer.pause()

    async def async_media_stop(self):
        """Stop and confirm."""
        if self._broadlink_entity:
            await self._send_broadlink_command("stop")
        else:
            await self._streamer.stop()

    async def async_set_volume_level(self, volume: float):
        """Set volume level and confirm."""
        vol_int = int(volume * 100)
        await self._streamer.set_volume(vol_int)

    async def async_mute_volume(self, mute: bool):
        """Mute/unmute and confirm."""
        await self._streamer.set_mute(mute)

    async def async_play_media(self, media_type: str, media_id: str, **kwargs):
        """Handle play_media service calls."""
        if media_type == "url":
            title = kwargs.get("title", "")
            artist = kwargs.get("artist", "")
            album = kwargs.get("album", "")
            album_art = kwargs.get("album_art", "")
            await self._streamer.play_url(media_id, title, artist, album, album_art)
        else:
            _LOGGER.warning("Unsupported media_type: %s", media_type)

    @property
    def media_title(self) -> str | None:
        """Return the title of current media."""
        return self.coordinator.data.get("media_title")

    @property
    def media_image_url(self) -> str | None:
        """Return the URL for the current album art."""
        return self.coordinator.data.get("media_image_url")

    @property
    def media_artist(self) -> str | None:
        """Return the artist of current media."""
        return self.coordinator.data.get("media_artist")

    @property
    def media_album_name(self) -> str | None:
        """Return the album name of current media."""
        return self.coordinator.data.get("media_album_name")

    @property
    def media_duration(self) -> int | None:
        """Return the duration in seconds."""
        return self.coordinator.data.get("media_duration")

    async def async_media_next_track(self):
        """Skip to the next track and confirm actual state."""
        if self._broadlink_entity:
            await self._send_broadlink_command("next")
        else:
            await self._streamer.next()

    async def async_media_previous_track(self):
        """Skip to the previous track and confirm actual state."""
        if self._broadlink_entity:
            await self._send_broadlink_command("previous")
        else:
            await self._streamer.previous()

    async def async_media_seek(self, position: int):
        """Handle media_seek service calls (position in seconds)."""
        await self._streamer.seek(position)

    async def async_select_source(self, source: str) -> None:
        if self._broadlink_entity:
            await self._send_broadlink_command(source.lower())
