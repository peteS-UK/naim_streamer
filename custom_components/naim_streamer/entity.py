"""Base class for Streamer Sensor entities."""

import logging

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import StreamerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class StreamerEntity(CoordinatorEntity[StreamerDataUpdateCoordinator]):
    """Defines a base status sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: StreamerDataUpdateCoordinator,
    ) -> None:
        """Initialize status sensor entity."""
        super().__init__(coordinator)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.uuid)},
            name=coordinator.streamer.name,
            manufacturer=coordinator.streamer.manufacturer,
            model=coordinator.streamer.model,
        )
