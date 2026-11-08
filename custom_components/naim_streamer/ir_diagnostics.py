"""Temporary controlled IR transmission service for receiver testing."""

import base64
import logging

import probatio
from homeassistant.components.infrared import async_send_command
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from infrared_protocols.commands import Command
from infrared_protocols.commands.rc5 import RC5Command

from .const import DOMAIN
from .coordinator import StreamerData
from .ir_codes import COMMANDS

_LOGGER = logging.getLogger(__name__)

SERVICE = "test_ir"
LEARNED = {
    "radio": "JgA2ABwdNzs4Ojg6ODo4OzceHAALOBoeODo3PDY8Nj02PDUhFwALOhseNzs3Ozc7Nzw2PTUhEQANBQ==",
    "stop": "JgBGAAQADIAcHhsdGx44Ozc7Gx0cHjc7Gx05AAs3GR8bHxoeNzs4OhsfGR83PBogNAALOhoeGh8aHzc7NzwZIBkfNj0ZHzUADQU=",
}
LEARNED_TOGGLE = {"radio": 0, "stop": 1}
SCHEMA = probatio.Schema(
    {
        probatio.Required("entity_id"): cv.entity_id,
        probatio.Required("button"): probatio.In(("radio", "stop")),
        probatio.Required("waveform"): probatio.In(("generated", "learned")),
        probatio.Optional("toggle", default=0): probatio.All(
            probatio.In((0, 1)), probatio.Coerce(int)
        ),
        probatio.Optional("frames", default=3): probatio.All(
            probatio.In(range(1, 11)), probatio.Coerce(int)
        ),
        probatio.Optional("period_ms", default=114): probatio.All(
            probatio.In(range(90, 131)), probatio.Coerce(int)
        ),
    }
)


class DiagnosticCommand(Command):
    """A fixed sequence of signed infrared timings."""

    def __init__(self, timings: list[int]) -> None:
        """Store the signal to be sent once."""
        super().__init__(modulation=36000)
        self._timings = timings

    def get_raw_timings(self) -> list[int]:
        """Return a copy of the encoded signal."""
        return self._timings.copy()


def _learned_timings(encoded: str) -> list[int]:
    """Decode Broadlink pulse lengths, excluding its final packet terminator."""
    data = base64.b64decode(encoded, validate=True)
    if data[:2] != b"\x26\x00" or len(data) != 4 + int.from_bytes(data[2:4], "little"):
        raise ValueError("Invalid learned Broadlink IR packet")
    if data[-3:] != b"\x00\x0d\x05":
        raise ValueError("Invalid learned Broadlink IR packet terminator")
    values = data[4:-3]
    pulses: list[int] = []
    index = 0
    while index < len(values):
        value = values[index]
        index += 1
        if value == 0:
            if index + 2 > len(values):
                raise ValueError("Incomplete Broadlink pulse duration")
            value = int.from_bytes(values[index : index + 2], "big")
            index += 2
        duration = round(value * 8192 / 269)
        pulses.append(duration if len(pulses) % 2 == 0 else -duration)
    if not pulses or len(pulses) % 2 != 1:
        raise ValueError("Invalid learned Broadlink pulse sequence")
    return pulses


def _generated_timings(
    button: str, toggle: int, frames: int, period_ms: int
) -> list[int]:
    """Build RC5 frames with a controlled start-to-start period."""
    template = COMMANDS[button]
    frame = RC5Command(
        address=template.address, command=template.command, toggle=toggle
    ).get_raw_timings()
    gap = period_ms * 1000 - sum(abs(value) for value in frame)
    return frame + ([-gap] + frame) * (frames - 1)


async def _async_test_ir(hass: HomeAssistant, call: ServiceCall) -> None:
    """Send one explicitly parameterized diagnostic signal."""
    entity = er.async_get(hass).async_get(call.data["entity_id"])
    if (
        entity is None
        or entity.platform != DOMAIN
        or entity.domain != "media_player"
        or entity.config_entry_id is None
    ):
        raise ServiceValidationError("Select a Naim Streamer media player entity")
    entry = hass.config_entries.async_get_entry(entity.config_entry_id)
    if (
        entry is None
        or entry.state != ConfigEntryState.LOADED
        or not isinstance(entry.runtime_data, StreamerData)
    ):
        raise ServiceValidationError("The selected Naim Streamer is not loaded")
    coordinator = entry.runtime_data.coordinator
    if not coordinator.infrared_entity_id:
        raise ServiceValidationError(
            "The selected Naim Streamer has no infrared emitter"
        )

    button = call.data["button"]
    waveform = call.data["waveform"]
    if waveform == "learned":
        toggle = LEARNED_TOGGLE[button]
        timings = _learned_timings(LEARNED[button])
        details = "captured waveform; frames=3; period approximately 110 ms"
    else:
        toggle = call.data["toggle"]
        frames = call.data["frames"]
        period_ms = call.data["period_ms"]
        timings = _generated_timings(button, toggle, frames, period_ms)
        details = f"frames={frames}; period={period_ms} ms"
    command = DiagnosticCommand(timings)
    async with coordinator._ir_send_lock:
        coordinator._ir_toggle_by_address[COMMANDS[button].address] = toggle
        _LOGGER.info(
            "IR test: entity=%s emitter=%s button=%s waveform=%s toggle=%d %s",
            call.data["entity_id"],
            coordinator.infrared_entity_id,
            button,
            waveform,
            toggle,
            details,
        )
        await async_send_command(hass, coordinator.infrared_entity_id, command)
        _LOGGER.info(
            "IR test send completed: entity=%s button=%s waveform=%s toggle=%d",
            call.data["entity_id"],
            button,
            waveform,
            toggle,
        )


def async_register_ir_diagnostics(hass: HomeAssistant) -> None:
    """Register the temporary diagnostic service."""

    async def handle(call: ServiceCall) -> None:
        await _async_test_ir(hass, call)

    hass.services.async_register(DOMAIN, SERVICE, handle, schema=SCHEMA)
