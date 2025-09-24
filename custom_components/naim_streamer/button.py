"""Platform for button integration for squeezebox."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import StreamerConfigEntry
from .coordinator import StreamerDataUpdateCoordinator
from .entity import StreamerEntity


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class StreamerButtonEntityDescription(ButtonEntityDescription):
    """Squeezebox Button description."""


STREAMER_BUTTON_ENTITIES: tuple[StreamerButtonEntityDescription, ...] = (
    StreamerButtonEntityDescription(
        key="play",
        icon="mdi:play",
        name="Play",
    ),
    StreamerButtonEntityDescription(
        name="Pause",
        icon="mdi:pause",
        key="pause",
    ),
    StreamerButtonEntityDescription(
        key="stop",
        icon="mdi:stop",
        name="Stop",
    ),
    StreamerButtonEntityDescription(
        key="next",
        icon="mdi:skip-next",
        name="Next",
    ),
    StreamerButtonEntityDescription(
        key="previous",
        icon="mdi:skip-previous",
        name="Previous",
    ),
    #    StreamerButtonEntityDescription(
    #        key="mute",
    #        icon="mdi:volume-off",
    #        name="Mute",
    #    ),
    #    StreamerButtonEntityDescription(
    #        name="Unmute",
    #        key="unmute",
    #        icon="mdi:volume-high",
    #    ),
    StreamerButtonEntityDescription(name="Display", key="disp"),
    StreamerButtonEntityDescription(name="One", key="one", icon="mdi:numeric-1"),
    StreamerButtonEntityDescription(name="Two", key="two", icon="mdi:numeric-2"),
    StreamerButtonEntityDescription(name="Three", key="three", icon="mdi:numeric-3"),
    StreamerButtonEntityDescription(name="Four", key="four", icon="mdi:numeric-4"),
    StreamerButtonEntityDescription(name="Five", key="five", icon="mdi:numeric-5"),
    StreamerButtonEntityDescription(name="Six", key="six", icon="mdi:numeric-6"),
    StreamerButtonEntityDescription(name="Seven", key="seven", icon="mdi:numeric-7"),
    StreamerButtonEntityDescription(name="Eight", key="eight", icon="mdi:numeric-8"),
    StreamerButtonEntityDescription(name="Nine", key="nine", icon="mdi:numeric-9"),
    StreamerButtonEntityDescription(name="Zero", key="zero", icon="mdi:numeric-0"),
    StreamerButtonEntityDescription(name="Preset", key="preset"),
    StreamerButtonEntityDescription(name="Store", key="store", icon="mdi:bookmark"),
    StreamerButtonEntityDescription(name="OK", key="ok"),
    StreamerButtonEntityDescription(name="Up", key="up", icon="mdi:arrow-up"),
    StreamerButtonEntityDescription(name="Down", key="down", icon="mdi:arrow-down"),
    StreamerButtonEntityDescription(name="Left", key="left", icon="mdi:arrow-left"),
    StreamerButtonEntityDescription(name="Right", key="right", icon="mdi:arrow-right"),
    StreamerButtonEntityDescription(name="Shuffle", key="shuffle", icon="mdi:shuffle"),
    StreamerButtonEntityDescription(name="Repeat", key="repeat", icon="mdi:repeat"),
    StreamerButtonEntityDescription(
        name="Info", key="info", icon="mdi:information-box"
    ),
    StreamerButtonEntityDescription(name="Setup", key="Setup"),
    StreamerButtonEntityDescription(name="Rewind", key="rewind", icon="mdi:rewind"),
    StreamerButtonEntityDescription(
        name="Fast Forward", key="fastforward", icon="mdi:fast-forward"
    ),
    StreamerButtonEntityDescription(name="CD", key="cd", icon="mdi:disc"),
    StreamerButtonEntityDescription(name="TV", key="tv", icon="mdi:television"),
    StreamerButtonEntityDescription(name="Radio", key="radio", icon="mdi:radio"),
    StreamerButtonEntityDescription(name="AUX", key="aux"),
    StreamerButtonEntityDescription(name="PC", key="pc", icon="mdi:laptop"),
    StreamerButtonEntityDescription(name="HDD", key="hdd", icon="mdi:harddisk"),
    StreamerButtonEntityDescription(name="iPod", key="ipod", icon="mdi:ipod"),
    StreamerButtonEntityDescription(
        name="Exit", key="exit", icon="mdi:keyboard-return"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: StreamerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup Button"""

    entities: list[StreamerButtonEntity] = []

    entities.extend(
        StreamerButtonEntity(
            coordinator=config_entry.runtime_data.coordinator,
            entity_description=description,
        )
        for description in STREAMER_BUTTON_ENTITIES
    )

    async_add_entities(entities)


class StreamerButtonEntity(StreamerEntity, ButtonEntity):
    """Representation of Buttons for Squeezebox entities."""

    entity_description: StreamerButtonEntityDescription

    def __init__(
        self,
        coordinator: StreamerDataUpdateCoordinator,
        entity_description: StreamerButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self.entity_description = entity_description
        self._attr_unique_id = self._coordinator.uuid + "_" + entity_description.key
        self._attr_name = entity_description.name
        self._attr_has_entity_name = True

    async def async_press(self) -> None:
        """Execute the button action."""
        _LOGGER.debug("Button pressed: %s", self.entity_description.key)
        await self._coordinator.async_send_command(self.entity_description.key)
