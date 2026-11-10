"""Tests for IR frame options and command transmission."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import probatio
import pytest
from homeassistant.helpers import config_validation as cv
from infrared_protocols.commands.rc5 import RC5Command

from custom_components.naim_streamer import async_unload_entry, config_flow, coordinator
from custom_components.naim_streamer.config_flow import (
    NaimStreamerConfigFlow,
    NaimStreamerOptionsFlow,
)
from custom_components.naim_streamer.const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_PREAMP_IR_FRAMES,
    CONF_STREAMER_IR_FRAMES,
)
from custom_components.naim_streamer.ir_codes import COMMANDS
from custom_components.naim_streamer.repairs import ReselectIREmitterFlow


def test_options_form_defaults_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The form defaults to two total frames and only accepts integers from 1 to 10."""
    entry = SimpleNamespace(data={}, options={})
    monkeypatch.setattr(config_flow, "async_get_emitters", lambda hass: [])
    monkeypatch.setattr(
        NaimStreamerOptionsFlow, "config_entry", property(lambda _: entry)
    )
    flow = NaimStreamerConfigFlow.async_get_options_flow(entry)
    flow.hass = object()
    flow.handler = "entry_id"
    flow.flow_id = "flow_id"
    result = asyncio.run(flow.async_step_init())
    schema = result["data_schema"]
    markers = {key.schema: key for key in schema.schema}
    for key in (CONF_STREAMER_IR_FRAMES, CONF_PREAMP_IR_FRAMES):
        assert markers[key].description["suggested_value"] == 2
    fields = probatio.to_field_list(schema, custom_serializer=cv.custom_serializer)
    assert {field["name"] for field in fields} == {
        CONF_INFRARED_ENTITY_ID,
        CONF_STREAMER_IR_FRAMES,
        CONF_PREAMP_IR_FRAMES,
    }
    for field in fields:
        if field["name"] != CONF_INFRARED_ENTITY_ID:
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
    entry = SimpleNamespace(
        data={}, options={CONF_STREAMER_IR_FRAMES: 3, "other": "value"}
    )
    monkeypatch.setattr(config_flow, "async_get_emitters", lambda hass: [])
    monkeypatch.setattr(
        NaimStreamerOptionsFlow, "config_entry", property(lambda _: entry)
    )
    flow = NaimStreamerOptionsFlow()
    flow.hass = object()
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
        CONF_INFRARED_ENTITY_ID: None,
        "other": "value",
    }


@pytest.mark.parametrize(
    ("data_emitter", "options", "expected"),
    [
        ("infrared.old", {}, "infrared.old"),
        ("infrared.old", {CONF_INFRARED_ENTITY_ID: "infrared.new"}, "infrared.new"),
        ("infrared.old", {CONF_INFRARED_ENTITY_ID: None}, None),
        (None, {}, None),
    ],
)
def test_options_emitter_selection(
    monkeypatch: pytest.MonkeyPatch,
    data_emitter: str | None,
    options: dict,
    expected: str | None,
) -> None:
    """Show the effective emitter and allow changing, adding, or clearing it."""
    entry = SimpleNamespace(
        data={CONF_INFRARED_ENTITY_ID: data_emitter}, options=options
    )
    monkeypatch.setattr(
        NaimStreamerOptionsFlow, "config_entry", property(lambda _: entry)
    )
    monkeypatch.setattr(
        config_flow, "async_get_emitters", lambda hass: ["infrared.new"]
    )
    flow = NaimStreamerOptionsFlow()
    flow.hass = object()
    flow.handler = "entry_id"
    flow.flow_id = "flow_id"
    assert flow.automatic_reload

    form = asyncio.run(flow.async_step_init())
    marker = next(
        key
        for key in form["data_schema"].schema
        if key.schema == CONF_INFRARED_ENTITY_ID
    )
    assert marker.description.get("suggested_value") == expected

    counts = {CONF_STREAMER_IR_FRAMES: 3, CONF_PREAMP_IR_FRAMES: 4}
    for selected in ("infrared.new", None):
        user_input = dict(counts)
        if selected:
            user_input[CONF_INFRARED_ENTITY_ID] = selected
        result = asyncio.run(flow.async_step_init(user_input))
        assert result["data"][CONF_INFRARED_ENTITY_ID] == selected
        assert result["data"][CONF_STREAMER_IR_FRAMES] == 3

    result = asyncio.run(
        flow.async_step_init({**counts, CONF_INFRARED_ENTITY_ID: "infrared.receiver"})
    )
    assert result["errors"]["base"] == "invalid_emitter"


def test_options_keep_temporarily_unavailable_emitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frame settings can be changed without replacing a missing current emitter."""
    entry = SimpleNamespace(
        data={CONF_INFRARED_ENTITY_ID: "infrared.old"}, options={}
    )
    monkeypatch.setattr(
        NaimStreamerOptionsFlow, "config_entry", property(lambda _: entry)
    )
    monkeypatch.setattr(config_flow, "async_get_emitters", lambda hass: [])
    flow = NaimStreamerOptionsFlow()
    flow.hass = object()
    flow.handler = "entry_id"
    flow.flow_id = "flow_id"
    form = asyncio.run(flow.async_step_init())
    fields = probatio.to_field_list(
        form["data_schema"], custom_serializer=cv.custom_serializer
    )
    emitter_field = next(
        field for field in fields if field["name"] == CONF_INFRARED_ENTITY_ID
    )
    assert emitter_field["selector"]["entity"]["include_entities"] == ["infrared.old"]
    result = asyncio.run(
        flow.async_step_init(
            {
                CONF_INFRARED_ENTITY_ID: "infrared.old",
                CONF_STREAMER_IR_FRAMES: 3,
                CONF_PREAMP_IR_FRAMES: 4,
            }
        )
    )
    assert result["data"][CONF_INFRARED_ENTITY_ID] == "infrared.old"


@pytest.mark.parametrize("old_emitter", [None, "infrared.old"])
def test_unload_uses_loaded_platforms(old_emitter: str | None) -> None:
    """Unload the platforms actually loaded, even after options change."""
    from homeassistant.const import Platform

    unload = AsyncMock(return_value=True)
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(infrared_entity_id=old_emitter)
        ),
        options={CONF_INFRARED_ENTITY_ID: None if old_emitter else "infrared.new"},
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_unload_platforms=unload)
    )
    assert asyncio.run(async_unload_entry(hass, entry))
    platforms = [Platform.MEDIA_PLAYER, Platform.SENSOR]
    if old_emitter:
        platforms.append(Platform.BUTTON)
    unload.assert_awaited_once_with(entry, platforms)


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, "infrared.old"),
        ({CONF_INFRARED_ENTITY_ID: "infrared.new"}, "infrared.new"),
        ({CONF_INFRARED_ENTITY_ID: None}, None),
    ],
)
def test_coordinator_uses_effective_emitter(
    monkeypatch: pytest.MonkeyPatch, options: dict, expected: str | None
) -> None:
    """The coordinator uses options first, including an explicit cleared value."""
    monkeypatch.setattr(
        coordinator.DataUpdateCoordinator, "__init__", lambda *a, **k: None
    )
    monkeypatch.setattr(coordinator, "async_get_clientsession", lambda hass: object())
    monkeypatch.setattr(coordinator, "NaimStreamerClient", lambda **kwargs: object())
    data = {
        "name": "NDX",
        "udn": "uuid",
        "manufacturer": "Naim",
        "model": "NDX",
        "port": "8080",
        "host": "127.0.0.1",
        "rendering_control_url": "http://example.test/rc",
        "av_transport_url": "http://example.test/av",
        "connection_manager_url": "http://example.test/cm",
        CONF_INFRARED_ENTITY_ID: "infrared.old",
    }
    entry = SimpleNamespace(data=data, options=options)
    instance = coordinator.StreamerDataUpdateCoordinator(object(), entry)
    assert instance.infrared_entity_id == expected


def test_repair_replaces_options_emitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A later migration repair cannot be shadowed by a previous options override."""
    from custom_components.naim_streamer import repairs

    entry = SimpleNamespace(
        entry_id="entry",
        title="NDX",
        data={"remote_entity": "remote.old", "remote_type": "broadlink"},
        options={CONF_INFRARED_ENTITY_ID: None, CONF_STREAMER_IR_FRAMES: 4},
    )
    update = Mock()
    reload_entry = AsyncMock(return_value=True)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_entry=lambda entry_id: entry,
            async_update_entry=update,
            async_reload=reload_entry,
        )
    )
    monkeypatch.setattr(repairs, "async_get_emitters", lambda hass: ["infrared.new"])
    flow = ReselectIREmitterFlow("entry")
    flow.hass = hass
    flow.flow_id = "flow_id"
    flow.handler = "naim_streamer"
    result = asyncio.run(
        flow.async_step_confirm({CONF_INFRARED_ENTITY_ID: "infrared.new"})
    )
    assert result["type"] == "create_entry"
    update.assert_called_once_with(
        entry,
        data={CONF_INFRARED_ENTITY_ID: "infrared.new"},
        options={CONF_STREAMER_IR_FRAMES: 4},
    )
    reload_entry.assert_awaited_once_with("entry")


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
