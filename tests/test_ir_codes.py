"""Tests for IR frame options and command transmission."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import probatio
import pytest
from homeassistant.helpers import config_validation as cv
from infrared_protocols.commands.rc5 import RC5Command

from custom_components.naim_streamer import coordinator
from custom_components.naim_streamer.config_flow import (
    NaimStreamerConfigFlow,
    NaimStreamerOptionsFlow,
)
from custom_components.naim_streamer.const import (
    CONF_PREAMP_IR_FRAMES,
    CONF_STREAMER_IR_FRAMES,
)
from custom_components.naim_streamer.ir_codes import COMMANDS


def test_options_form_defaults_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The form defaults to two total frames and only accepts integers from 1 to 10."""
    entry = SimpleNamespace(options={})
    monkeypatch.setattr(
        NaimStreamerOptionsFlow, "config_entry", property(lambda _: entry)
    )
    flow = NaimStreamerConfigFlow.async_get_options_flow(entry)
    flow.handler = "entry_id"
    flow.flow_id = "flow_id"
    result = asyncio.run(flow.async_step_init())
    schema = result["data_schema"]
    markers = {key.schema: key for key in schema.schema}
    for key in (CONF_STREAMER_IR_FRAMES, CONF_PREAMP_IR_FRAMES):
        assert markers[key].description["suggested_value"] == 2
    fields = probatio.to_field_list(schema, custom_serializer=cv.custom_serializer)
    assert {field["name"] for field in fields} == {
        CONF_STREAMER_IR_FRAMES,
        CONF_PREAMP_IR_FRAMES,
    }
    for field in fields:
        assert field["selector"]["number"]["min"] == 1
        assert field["selector"]["number"]["max"] == 10
    assert schema({CONF_STREAMER_IR_FRAMES: 1, CONF_PREAMP_IR_FRAMES: 10}) == {
        CONF_STREAMER_IR_FRAMES: 1,
        CONF_PREAMP_IR_FRAMES: 10,
    }
    assert (
        type(
            schema({CONF_STREAMER_IR_FRAMES: 1.0, CONF_PREAMP_IR_FRAMES: 2.0})[
                CONF_STREAMER_IR_FRAMES
            ]
        )
        is int
    )
    for invalid in (0, 11, 1.5):
        with pytest.raises(probatio.Invalid):
            schema({CONF_STREAMER_IR_FRAMES: invalid, CONF_PREAMP_IR_FRAMES: 2})


def test_options_form_preserves_and_saves_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reopening shows saved counts and saving preserves unrelated options."""
    entry = SimpleNamespace(options={CONF_STREAMER_IR_FRAMES: 3, "other": "value"})
    monkeypatch.setattr(
        NaimStreamerOptionsFlow, "config_entry", property(lambda _: entry)
    )
    flow = NaimStreamerOptionsFlow()
    flow.handler = "entry_id"
    flow.flow_id = "flow_id"
    form = asyncio.run(flow.async_step_init())
    markers = {key.schema: key for key in form["data_schema"].schema}
    assert markers[CONF_STREAMER_IR_FRAMES].description["suggested_value"] == 3
    assert markers[CONF_PREAMP_IR_FRAMES].description["suggested_value"] == 2
    result = asyncio.run(
        flow.async_step_init({CONF_STREAMER_IR_FRAMES: 4, CONF_PREAMP_IR_FRAMES: 5})
    )
    assert result["data"] == {
        CONF_STREAMER_IR_FRAMES: 4,
        CONF_PREAMP_IR_FRAMES: 5,
        "other": "value",
    }


def test_command_frames_and_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Options apply independently and immediately without changing the RC5 toggle."""
    sender = AsyncMock()
    monkeypatch.setattr(coordinator, "async_send_command", sender)

    async def exercise() -> None:
        instance = coordinator.StreamerDataUpdateCoordinator.__new__(
            coordinator.StreamerDataUpdateCoordinator
        )
        instance.hass = object()
        instance.config_entry = SimpleNamespace(options={})
        instance.infrared_entity_id = "infrared.test"
        instance._ir_toggle_by_address = {}
        instance._ir_send_lock = asyncio.Lock()

        await instance._send_remote_command("radio")
        await instance._send_remote_command("mute")
        instance.config_entry.options = {
            CONF_STREAMER_IR_FRAMES: 3,
            CONF_PREAMP_IR_FRAMES: 1,
        }
        await instance._send_remote_command("radio")
        await instance._send_remote_command("mute")
        await instance._send_remote_command("radio")

    asyncio.run(exercise())
    for call, key, count, toggle in zip(
        sender.await_args_list,
        ("radio", "mute", "radio", "mute", "radio"),
        (2, 2, 3, 1, 3),
        (0, 0, 1, 1, 0),
        strict=True,
    ):
        command = call.args[2]
        template = COMMANDS[key]
        assert (
            command.address,
            command.command,
            command.toggle,
            command.repeat_count,
        ) == (
            template.address,
            template.command,
            toggle,
            count - 1,
        )
        frame = RC5Command(
            address=command.address, command=command.command, toggle=toggle
        ).get_raw_timings()
        timings = command.get_raw_timings()
        for index in range(count):
            start = index * (len(frame) + 1)
            assert timings[start : start + len(frame)] == frame
            if index:
                assert timings[start - 1] < 0
        assert len(timings) == count * len(frame) + count - 1


def test_command_debug_logging(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Log the generated timings and the parameters sent to the emitter."""
    sender = AsyncMock()
    monkeypatch.setattr(coordinator, "async_send_command", sender)

    async def exercise() -> None:
        instance = coordinator.StreamerDataUpdateCoordinator.__new__(
            coordinator.StreamerDataUpdateCoordinator
        )
        instance.hass = object()
        instance.config_entry = SimpleNamespace(options={CONF_STREAMER_IR_FRAMES: 3})
        instance.infrared_entity_id = "infrared.test"
        instance._ir_toggle_by_address = {}
        instance._ir_send_lock = asyncio.Lock()
        await instance._send_remote_command("radio")

    with caplog.at_level(logging.DEBUG, logger=coordinator.__name__):
        asyncio.run(exercise())

    command = sender.await_args.args[2]
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "Sending RC5 command radio to infrared.test" in message
    assert "address=21 command=20 toggle=0 frames=3 carrier=36000 Hz" in message
    assert f"timings_us={command.get_raw_timings()}" in message
