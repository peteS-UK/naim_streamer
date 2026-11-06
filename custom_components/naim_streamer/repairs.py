"""Repair flows for Naim Streamer."""

from __future__ import annotations

import probatio
from homeassistant import data_entry_flow
from homeassistant.components.infrared import (
    DOMAIN as INFRARED_DOMAIN,
    async_get_emitters,
)
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_INFRARED_ENTITY_ID

LEGACY_REMOTE_KEYS = ("remote_entity", "remote_type")


class ReselectIREmitterFlow(RepairsFlow):
    """Ask the user to choose an infrared emitter to replace the legacy remote."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        emitters = async_get_emitters(self.hass)
        if not emitters:
            return self.async_abort(reason="no_emitters")

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_not_found")

        if user_input is not None:
            data = {
                k: v for k, v in entry.data.items() if k not in LEGACY_REMOTE_KEYS
            }
            data[CONF_INFRARED_ENTITY_ID] = user_input[CONF_INFRARED_ENTITY_ID]
            self.hass.config_entries.async_update_entry(entry, data=data)
            # Reloading re-evaluates the issue, which deletes it.
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_INFRARED_ENTITY_ID): EntitySelector(
                        EntitySelectorConfig(
                            domain=INFRARED_DOMAIN, include_entities=emitters
                        )
                    )
                }
            ),
            description_placeholders={"name": entry.title},
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    """Create the fix flow for a Naim Streamer issue."""
    assert data is not None
    return ReselectIREmitterFlow(str(data["entry_id"]))
