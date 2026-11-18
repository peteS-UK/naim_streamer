"""Audio format sensor for Naim streamers."""

# pyright: reportIncompatibleVariableOverride=false

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import StreamerConfigEntry, StreamerDataUpdateCoordinator
from .entity import StreamerEntity

SENSORS = (
    SensorEntityDescription(
        key="format",
        translation_key="format",
        icon="mdi:file-music",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StreamerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the audio format sensor and remove retired sensors."""
    registry = er.async_get(hass)
    for key in ("bitrate", "sample_frequency", "bit_depth"):
        entity_id = registry.async_get_entity_id(
            "sensor",
            DOMAIN,
            f"{config_entry.runtime_data.coordinator.uuid}_audio_{key}",
        )
        if entity_id is not None:
            registry.async_remove(entity_id)
    async_add_entities(
        [
            StreamerAudioSensor(config_entry.runtime_data.coordinator, description)
            for description in SENSORS
        ]
    )


class StreamerAudioSensor(StreamerEntity, SensorEntity):
    """A property of the currently playing audio resource."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: StreamerDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.uuid}_audio_{description.key}"

    @property
    def native_value(self) -> str | None:
        """Return the most recently reported value."""
        return self.coordinator.audio_format
