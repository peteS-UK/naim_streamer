"""Platform for button integration for squeezebox."""

# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import StreamerConfigEntry, StreamerDataUpdateCoordinator
from .entity import StreamerEntity
from .ir_codes import BUTTONS

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class StreamerButtonEntityDescription(ButtonEntityDescription):
    """Squeezebox Button description."""


STREAMER_BUTTON_ENTITIES: tuple[StreamerButtonEntityDescription, ...] = tuple(
    StreamerButtonEntityDescription(key=b.key, name=b.name, icon=b.icon)
    for b in BUTTONS
    if b.has_button
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

    _entity_description: StreamerButtonEntityDescription

    def __init__(
        self,
        coordinator: StreamerDataUpdateCoordinator,
        entity_description: StreamerButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._entity_description = entity_description
        self._attr_unique_id = self._coordinator.uuid + "_" + entity_description.key
        self._attr_name = str(entity_description.name)
        self._attr_has_entity_name = True

    async def async_press(self) -> None:
        """Execute the button action."""
        _LOGGER.debug("Button pressed: %s", self._entity_description.key)
        await self._coordinator.async_send_command(self._entity_description.key)
