import logging

from homeassistant import config_entries, core
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers import issue_registry as ir

from .const import CONF_INFRARED_ENTITY_ID, DOMAIN
from .coordinator import (
    StreamerConfigEntry,
    StreamerData,
    StreamerDataUpdateCoordinator,
)

_LOGGER = logging.getLogger(__name__)


def _platforms_for_entry(config_entry: ConfigEntry) -> list[Platform]:
    """Return the platforms to load; buttons need an infrared emitter."""
    platforms = [Platform.MEDIA_PLAYER, Platform.SENSOR]
    if config_entry.data.get(CONF_INFRARED_ENTITY_ID):
        platforms.append(Platform.BUTTON)
    return platforms


def _update_legacy_remote_issue(
    hass: core.HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Raise a repair issue if the entry still uses a legacy Broadlink/Tuya remote."""
    issue_id = f"reselect_ir_emitter_{config_entry.entry_id}"
    uses_legacy = bool(config_entry.data.get("remote_entity")) and not (
        config_entry.data.get(CONF_INFRARED_ENTITY_ID)
    )
    if uses_legacy:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="reselect_ir_emitter",
            translation_placeholders={"name": config_entry.title},
            data={"entry_id": config_entry.entry_id},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


async def async_setup_entry(
    hass: core.HomeAssistant, config_entry: StreamerConfigEntry
) -> bool:
    """Set up platform from a ConfigEntry."""

    hass.data.setdefault(DOMAIN, {})
    _update_legacy_remote_issue(hass, config_entry)
    # hass_data = dict(config_entry.data)
    # hass.data[DOMAIN][config_entry.entry_id] = hass_data

    coordinator = StreamerDataUpdateCoordinator(hass, config_entry)

    config_entry.runtime_data = StreamerData(coordinator=coordinator)
    # Runs on unload and also if setup fails (e.g. ConfigEntryNotReady), so the
    # callback server and subscriptions are never leaked.
    config_entry.async_on_unload(coordinator.async_unload)
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(
        config_entry, _platforms_for_entry(config_entry)
    )

    return True


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""

    # The coordinator is cleaned up by the on_unload callback registered in setup,
    # which only runs once the platforms have unloaded successfully.
    return await hass.config_entries.async_unload_platforms(
        entry, _platforms_for_entry(entry)
    )
