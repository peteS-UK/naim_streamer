class NaimStreamerDevice(StreamerEntity, MediaPlayerEntity):
    # Representation of a Naim Streamer

    def __init__(self, device, hass, broadlink_entity):
        self._device = device
        self._hass = hass
        self._state = MediaPlayerState.IDLE
        # self._entity_id = "media_player.naim_ndx"
        self._unique_id = self._device.udn
        self._device_class = "receiver"
        self._name = self._device.name
        self._broadlink_entity = broadlink_entity
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
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._unique_id)
            },
            name=self._name,
            manufacturer=self._device.manufacturer,
            model=self._device.model,
        )

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

    async def send_command(self, command):
        await self._send_broadlink_command(command)

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

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set the repeat mode."""
        if repeat == RepeatMode.ONE:
            await self._send_broadlink_command("repeat")
            self.async_schedule_update_ha_state()

    async def async_media_stop(self) -> None:
        """Send stop command to media player."""
        await self._send_broadlink_command("stop")
        self._state = MediaPlayerState.IDLE
        self.async_schedule_update_ha_state()

    async def async_media_play(self) -> None:
        """Send play command to media player."""
        await self._send_broadlink_command("play")
        self._state = MediaPlayerState.PLAYING
        self.async_schedule_update_ha_state()

    async def async_media_pause(self) -> None:
        """Send pause command to media player."""
        await self._send_broadlink_command("pause")
        self._state = MediaPlayerState.PAUSED
        self.async_schedule_update_ha_state()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self._send_broadlink_command("next")

    async def async_media_previous_track(self) -> None:
        """Send next track command."""
        await self._send_broadlink_command("previous")

    async def async_select_source(self, source: str) -> None:
        await self._send_broadlink_command(source.lower())

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffle mode."""
        self._shuffle = not self._shuffle
        await self._send_broadlink_command("shuffle")
        await self.coordinator.async_refresh()
