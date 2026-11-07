"""Coordinator for Naim Streamer integration."""

import asyncio
import html
import logging
import re
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import urljoin

from aiohttp import ClientTimeout, web
from homeassistant.components.infrared import async_send_command
from homeassistant.components.media_player.const import MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_MANUFACTURER, CONF_MODEL, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from infrared_protocols.commands.rc5 import RC5Command
from lxml import etree

from .const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_PREAMP_IR_FRAMES,
    CONF_STREAMER_IR_FRAMES,
    DEFAULT_IR_FRAMES,
    DOMAIN,
)
from .ir_codes import COMMANDS, PREAMP_ADDRESS, STREAMER_ADDRESS
from .naim_streamer_client import NaimStreamerClient

TRANSPORT_TO_HA_STATE = {
    "STOPPED": MediaPlayerState.IDLE,
    "NO_MEDIA_PRESENT": MediaPlayerState.IDLE,
    "PLAYING": MediaPlayerState.PLAYING,
    "PAUSED_PLAYBACK": MediaPlayerState.PAUSED,
    "TRANSITIONING": MediaPlayerState.PLAYING,
}


@dataclass
class StreamerData:
    coordinator: "StreamerDataUpdateCoordinator"


type StreamerConfigEntry = ConfigEntry[StreamerData]

DEFAULT_TIMEOUT = 10
NOTIFY_WAIT_SECONDS = 30
POSITION_REFRESH_SECONDS = 30
_LOGGER = logging.getLogger(__name__)


class StreamerDataUpdateCoordinator(DataUpdateCoordinator):
    """Streamer coordinator with UPnP event subscription."""

    config_entry: StreamerConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: StreamerConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=config_entry.data[CONF_NAME],
            update_interval=timedelta(minutes=5),  # fallback poll
            always_update=False,
        )
        self.hass = hass
        self.config_entry = config_entry
        self._session = async_get_clientsession(hass)
        self.streamer = NaimStreamerClient(
            session=self._session,
            name=self.config_entry.data["name"],
            udn=self.config_entry.data["udn"],
            manufacturer=self.config_entry.data[ATTR_MANUFACTURER],
            model=self.config_entry.data[CONF_MODEL],
            port=self.config_entry.data[CONF_PORT],
            rendering_control_url=self.config_entry.data["rendering_control_url"],
            av_transport_url=self.config_entry.data["av_transport_url"],
            connection_manager_url=self.config_entry.data["connection_manager_url"],
            host=self.config_entry.data["host"],
        )
        self.sid_av = None
        self.sid_rc = None
        self._runner = None
        self._site = None
        self._callback_url = ""
        self._notify_received = False
        self._warned_no_notify = False
        self._notify_watch = None
        self.data = {}
        self.infrared_entity_id = config_entry.data.get(CONF_INFRARED_ENTITY_ID)
        self._ir_toggle_by_address: dict[int, int] = {}
        self._ir_send_lock = asyncio.Lock()
        self.media_position: int | None = None
        self.media_position_updated_at: datetime | None = None
        self._position_refresh_requested = asyncio.Event()
        self._position_generation = 0
        self.uuid = self.config_entry.data["udn"]

    async def _async_setup(self):
        """Initialise client and subscribe to events."""

        self.config_entry.async_create_background_task(
            self.hass,
            self._position_refresh_loop(),
            name=f"{DOMAIN} position refresh",
        )

        # Start local aiohttp server for NOTIFY callbacks
        app = web.Application()
        app.router.add_route("NOTIFY", "/upnp/event", self._handle_notify)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", 0)
        await self._site.start()
        assert self._site._server is not None
        server = cast(Any, self._site._server)
        port = server.sockets[0].getsockname()[1]
        local_ip = self._get_local_ip(self.streamer.host)

        callback_url = f"http://{local_ip}:{port}/upnp/event"
        self._callback_url = callback_url
        _LOGGER.debug("Callback URL: %s", callback_url)

        _LOGGER.debug("Config entry data: %s", self.config_entry.data)

        _LOGGER.debug(
            "Subscribing AVTransport to %s",
            self.config_entry.data["av_transport_event_url"],
        )
        _LOGGER.debug(
            "Subscribing RenderingControl to %s",
            self.config_entry.data["rendering_control_event_url"],
        )

        try:
            self.sid_av = await self.streamer.subscribe_service(
                self.config_entry.data["av_transport_event_url"], callback_url
            )
            self.sid_rc = await self.streamer.subscribe_service(
                self.config_entry.data["rendering_control_event_url"], callback_url
            )
            if self.sid_av and self.sid_rc:
                self._after_subscribe()
            else:
                self._apply_poll_mode()
            self.config_entry.async_create_background_task(
                self.hass,
                self._renew_loop(callback_url),
                name=f"{DOMAIN} subscription renewal",
            )
        except Exception:
            _LOGGER.exception("Subscription failed, using fast poll:")
            self.update_interval = timedelta(seconds=30)

        _LOGGER.debug("AVTransport SID: %s", self.sid_av)
        _LOGGER.debug("RenderingControl SID: %s", self.sid_rc)

        # return await self._async_update_data()

    async def async_send_command(self, command):
        if command == "play":
            await self.async_play()
        elif command == "pause":
            await self.async_pause()
        elif command == "stop":
            await self.async_stop()
        elif command == "next":
            await self.async_next_track()
        elif command == "previous":
            await self.async_previous_track()
        elif self.infrared_entity_id:
            await self._send_remote_command(command)
        else:
            raise ServiceValidationError(
                f"{command} is only supported with an infrared emitter"
            )

    async def _send_remote_command(self, command):
        if command not in COMMANDS:
            raise ServiceValidationError(f"Unknown command: {command}")
        if not self.infrared_entity_id:
            raise ServiceValidationError("An infrared emitter is required")
        template = COMMANDS[command]
        async with self._ir_send_lock:
            toggle = 1 - self._ir_toggle_by_address.get(template.address, 1)
            self._ir_toggle_by_address[template.address] = toggle
            rc5_command = RC5Command(
                address=template.address,
                command=template.command,
                toggle=toggle,
                modulation=template.modulation,
                repeat_count=self.config_entry.options.get(
                    {
                        STREAMER_ADDRESS: CONF_STREAMER_IR_FRAMES,
                        PREAMP_ADDRESS: CONF_PREAMP_IR_FRAMES,
                    }[template.address],
                    DEFAULT_IR_FRAMES,
                )
                - 1,
            )
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(
                    "Sending RC5 command %s to %s: address=%d command=%d toggle=%d "
                    "frames=%d carrier=%d Hz timings_us=%s",
                    command,
                    self.infrared_entity_id,
                    rc5_command.address,
                    rc5_command.command,
                    rc5_command.toggle,
                    rc5_command.repeat_count + 1,
                    rc5_command.modulation,
                    rc5_command.get_raw_timings(),
                )
            await async_send_command(self.hass, self.infrared_entity_id, rc5_command)

    async def async_play(self):
        if self.infrared_entity_id:
            await self._send_remote_command("play")
        else:
            if not self.streamer.last_uri or self.streamer.status == "ERROR_OCCURRED":
                uri = self.data.get("media_uri") or self.streamer.last_uri
                metadata = (
                    self.data.get("media_metadata") or self.streamer.last_metadata
                )

                if uri and metadata:
                    _LOGGER.debug("Restoring AVTransport URI before play: %s", uri)
                    await self.streamer.set_av_transport_uri(uri, metadata=metadata)
                else:
                    _LOGGER.warning("No stored URI/metadata to restore before play")

            await self.streamer.play()

    async def async_pause(self):
        """Pause and confirm."""
        if self.infrared_entity_id:
            await self._send_remote_command("play")
        else:
            await self.streamer.pause()

    async def async_volume_up(self):
        """Pause and confirm."""
        if self.infrared_entity_id:
            await self._send_remote_command("vol+")

    async def async_volume_down(self):
        """Pause and confirm."""
        if self.infrared_entity_id:
            await self._send_remote_command("vol-")

    async def async_mute_toggle(self):
        """Pause and confirm."""
        if self.infrared_entity_id:
            await self._send_remote_command("mute")

    async def async_stop(self):
        """Stop and confirm."""
        if self.infrared_entity_id:
            await self._send_remote_command("stop")
        else:
            await self.streamer.stop()

    async def async_next_track(self):
        """Skip to the next track and confirm actual state."""
        if self.infrared_entity_id:
            await self._send_remote_command("next")
        else:
            await self.streamer.next()

    async def async_previous_track(self):
        """Skip to the previous track and confirm actual state."""
        if self.infrared_entity_id:
            await self._send_remote_command("previous")
        else:
            await self.streamer.previous()

    def _apply_poll_mode(self) -> None:
        """Poll as a fallback unless subscriptions work and events are arriving."""
        if self.sid_av and self.sid_rc and self._notify_received:
            self.update_interval = None
        else:
            self.update_interval = timedelta(seconds=30)

    def _after_subscribe(self) -> None:
        """Reset event tracking after a (re)subscribe and watch for the first NOTIFY."""
        self._notify_received = False
        self._apply_poll_mode()
        if self._notify_watch:
            self._notify_watch()
        self._notify_watch = async_call_later(
            self.hass, NOTIFY_WAIT_SECONDS, self._check_notify_received
        )

    @callback
    def _check_notify_received(self, _now) -> None:
        self._notify_watch = None
        if self._notify_received:
            return
        message = (
            "No event received from the streamer %s s after subscribing; "
            "it may be unable to reach Home Assistant at %s. "
            "Falling back to polling"
        )
        if self._warned_no_notify:
            _LOGGER.debug(message, NOTIFY_WAIT_SECONDS, self._callback_url)
        else:
            self._warned_no_notify = True
            _LOGGER.warning(message, NOTIFY_WAIT_SECONDS, self._callback_url)

    def _renew_interval(self, requested: int) -> float:
        """Renew at half the lifetime the device granted (or requested if unknown)."""
        lifetime = self.streamer.subscription_timeout or requested
        return max(15, min(requested - 60, lifetime / 2))

    async def _renew_loop(self, callback_url: str):
        timeout = 300
        try:
            while True:
                await asyncio.sleep(self._renew_interval(timeout))
                try:
                    if self.sid_av:
                        self.sid_av = await self.streamer.renew_subscription(
                            self.config_entry.data["av_transport_event_url"],
                            self.sid_av,
                            timeout,
                        )
                    if self.sid_rc:
                        self.sid_rc = await self.streamer.renew_subscription(
                            self.config_entry.data["rendering_control_event_url"],
                            self.sid_rc,
                            timeout,
                        )
                    self._apply_poll_mode()
                except Exception:
                    _LOGGER.warning("Renewal failed, re-subscribing:", exc_info=True)
                    # Try full re‑subscribe
                    try:
                        self.sid_av = await self.streamer.subscribe_service(
                            self.config_entry.data["av_transport_event_url"],
                            callback_url,
                            timeout,
                        )
                        self.sid_rc = await self.streamer.subscribe_service(
                            self.config_entry.data["rendering_control_event_url"],
                            callback_url,
                            timeout,
                        )
                        self._after_subscribe()
                    except Exception:
                        _LOGGER.exception("Re‑subscribe failed:")
                        self.update_interval = timedelta(seconds=30)
        except asyncio.CancelledError:
            _LOGGER.debug("Renewal loop cancelled")
            raise

    async def _handle_notify(self, request):
        body = await request.text()
        _LOGGER.debug("Received from %s NOTIFY:\n%s", request.remote, body)

        if not self._notify_received:
            self._notify_received = True
            self._warned_no_notify = False
            self._apply_poll_mode()

        ns = {"e": "urn:schemas-upnp-org:event-1-0"}

        try:
            root = ET.fromstring(body)
        except ET.ParseError as err:
            _LOGGER.warning(
                "Ignoring malformed NOTIFY XML from %s: %s", request.remote, err
            )
            return web.Response(status=200)

        # Detect service type from payload
        if "urn:schemas-upnp-org:metadata-1-0/AVT/" in body:
            service_type = "avtransport"
        elif "urn:schemas-upnp-org:metadata-1-0/RenderingControl/" in body:
            service_type = "renderingcontrol"
        else:
            service_type = "unknown"

        if service_type == "avtransport":
            has_last_change = False
            for prop in root.findall(".//e:property", ns):
                for child in prop:
                    if child.tag == "LastChange" and (child.text or "").strip():
                        assert child.text is not None
                        self._parse_last_change(child.text)
                        has_last_change = True
            if has_last_change:
                self.request_position_refresh()

        elif service_type == "renderingcontrol":
            for prop in root.findall(".//e:property", ns):
                for child in prop:
                    tag = child.tag
                    val = child.text or ""
                    if tag == "CurrentVolume" and val.strip():
                        self.data["volume"] = int(val)
                    elif tag == "Mute" and val.strip():
                        self.data["mute"] = bool(int(val))

        _LOGGER.debug("Coordinator data after NOTIFY: %s", self.data)
        self.async_update_listeners()

        return web.Response(status=200)

    @callback
    def request_position_refresh(self) -> None:
        """Invalidate stale positions and request an updated sample."""
        self._position_generation += 1
        self.media_position = None
        self.media_position_updated_at = None
        self._position_refresh_requested.set()

    @staticmethod
    def _parse_position(value: str) -> int | None:
        """Parse a UPnP RelTime, treating unavailable values as unknown."""
        match = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d)(?:\.\d+)?", value)
        if not match:
            return None
        hours, minutes, seconds = (int(part) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds

    async def _position_refresh_loop(self) -> None:
        """Fetch position on changes and periodically while playing."""
        while True:
            if self.data.get("state") == MediaPlayerState.PLAYING:
                try:
                    await asyncio.wait_for(
                        self._position_refresh_requested.wait(),
                        timeout=POSITION_REFRESH_SECONDS,
                    )
                except TimeoutError:
                    pass
            else:
                await self._position_refresh_requested.wait()
            self._position_refresh_requested.clear()
            generation = self._position_generation
            try:
                async with asyncio.timeout(DEFAULT_TIMEOUT):
                    position_info = await self.streamer.get_position_info()
            except TimeoutError:
                _LOGGER.warning("Timed out fetching playback position")
                position_info = None
            if generation != self._position_generation:
                continue
            raw_position = (
                position_info.get("RelTime") if isinstance(position_info, dict) else None
            )
            position = (
                self._parse_position(raw_position)
                if isinstance(raw_position, str)
                else None
            )
            if position is None:
                _LOGGER.debug("Playback position unavailable: %s", raw_position)
            self.media_position = position
            self.media_position_updated_at = (
                dt_util.utcnow() if position is not None else None
            )
            self.async_update_listeners()

    def _parse_rendering_control(self, val: str):
        """Parse RenderingControl LastChange XML for volume/mute only."""
        try:
            inner_xml = html.unescape(html.unescape(val))
            parser = etree.XMLParser(recover=True)
            rc_root = etree.fromstring(inner_xml.encode("utf-8"), parser=parser)

            inst_elems = rc_root.xpath(".//*[local-name()='InstanceID']")
            if not inst_elems:
                return
            inst = inst_elems[0]

            vol_elems = inst.xpath(".//*[local-name()='CurrentVolume']")
            if vol_elems:
                self.data["volume"] = int(vol_elems[0].attrib.get("val", "0"))

            mute_elems = inst.xpath(".//*[local-name()='Mute']")
            if mute_elems:
                self.data["mute"] = bool(int(mute_elems[0].attrib.get("val", "0")))

        except etree.XMLSyntaxError as e:
            _LOGGER.warning("Failed to parse RenderingControl XML (lxml): %s", e)

    def _parse_last_change(self, val: str):
        # Get raw CurrentTrackMetaData DIDL from the unparsed LastChange string
        m = re.search(r'CurrentTrackMetaData\s+val="([^"]+)"', val)
        if m:
            raw_val = m.group(1)
            didl_xml = html.unescape(html.unescape(raw_val))
            self._parse_didl_metadata(didl_xml)

        # Get raw NextAVTransportURIMetaData DIDL
        m = re.search(r'NextAVTransportURIMetaData\s+val="([^"]+)"', val)
        if m:
            raw_val = m.group(1)
            didl_xml = html.unescape(html.unescape(raw_val))
            self._parse_didl_metadata(didl_xml, prefix="next_")

        # Now parse LastChange normally for state/duration
        inner_xml = html.unescape(html.unescape(val))
        parser = etree.XMLParser(recover=True)
        lc_root = etree.fromstring(inner_xml.encode("utf-8"), parser=parser)

        inst_elems = lc_root.xpath(".//*[local-name()='InstanceID']")
        if not inst_elems:
            return
        inst = inst_elems[0]

        ts_elems = inst.xpath(".//*[local-name()='TransportState']")
        if ts_elems:
            self.data["state"] = TRANSPORT_TO_HA_STATE.get(
                ts_elems[0].attrib.get("val", "").upper(), MediaPlayerState.IDLE
            )
            self.streamer.state = self.data["state"]

        ts_elems = inst.xpath(".//*[local-name()='TransportStatus']")
        if ts_elems:
            self.data["status"] = ts_elems[0].attrib.get("val", "").upper()
            self.streamer.status = self.data["status"]

        dur_elems = inst.xpath(".//*[local-name()='CurrentTrackDuration']")
        if dur_elems:
            self.data["media_duration"] = self._parse_duration(
                dur_elems[0].attrib.get("val", "")
            )

    def _parse_didl_metadata(self, didl_xml: str, prefix: str = ""):
        try:
            # Ensure any bare ampersands are XML-safe
            didl_xml = didl_xml.replace("&", "&amp;").replace("&amp;amp;", "&amp;")

            parser = etree.XMLParser(recover=True)
            didl_root = etree.fromstring(didl_xml.encode("utf-8"), parser=parser)

            # Strip namespaces for easier XPath
            for elem in didl_root.iter():
                if "}" in elem.tag:
                    elem.tag = elem.tag.split("}", 1)[1]

            _LOGGER.debug(
                "Cleaned DIDL XML:\n%s",
                etree.tostring(didl_root, pretty_print=True).decode(),
            )

            def find_text_local(root, local):
                el = root.find(f".//{local}")
                return el.text if el is not None else ""

            # Core metadata
            self.data[f"{prefix}media_title"] = find_text_local(didl_root, "title")
            self.data[f"{prefix}media_artist"] = find_text_local(
                didl_root, "artist"
            ) or find_text_local(didl_root, "creator")
            self.data[f"{prefix}media_album_name"] = find_text_local(didl_root, "album")

            # Duration
            res_el = didl_root.find(".//res")
            if res_el is not None and "duration" in res_el.attrib:
                self.data[f"{prefix}media_duration"] = self._parse_duration(
                    res_el.attrib["duration"]
                )

            # Album art — normalise relative URLs
            album_art = find_text_local(didl_root, "albumArtURI")
            if album_art:
                if album_art.startswith("/"):
                    album_art = urljoin(self.streamer.base_url, album_art)
                self.data[f"{prefix}media_image_url"] = album_art

            # Current URI to enable play after pause
            current_uri = find_text_local(didl_root, "res")
            if current_uri:
                self.data["current_uri"] = current_uri
                self.data["current_metadata"] = didl_xml  # raw DIDL for reuse
                # Persist to streamer
                self.streamer.last_uri = current_uri
                self.streamer.last_metadata = didl_xml

        except etree.XMLSyntaxError as e:
            _LOGGER.warning("Failed to parse DIDL-Lite metadata (lxml): %s", e)

    async def _async_update_data(self):
        """Fallback polling."""
        try:
            vol_data = await self.streamer.get_volume(parsed=True)
            mute_data = await self.streamer.get_mute(parsed=True)
            transport_data = await self.streamer.get_transport_info(parsed=True)
            media_info = await self.streamer.get_media_info(parsed=True)

            if isinstance(transport_data, dict):
                raw_state = transport_data.get(
                    "CurrentTransportState", "UNKNOWN"
                ).upper()
            else:
                raw_state = (
                    transport_data.upper()
                    if isinstance(transport_data, str)
                    else "UNKNOWN"
                )

            if isinstance(vol_data, dict) and "CurrentVolume" in vol_data:
                _vol = int(vol_data.get("CurrentVolume", 0))
            else:
                _vol = self.data.get("volume", 0)

            if not isinstance(mute_data, dict):
                mute_data = {}

            if not isinstance(media_info, dict):
                media_info = {}

            result = {
                "volume": int(_vol),
                "mute": bool(
                    int(mute_data.get("CurrentMute", int(self.data.get("mute", False))))
                ),
                "state": TRANSPORT_TO_HA_STATE.get(raw_state, MediaPlayerState.IDLE),
                "media_title": media_info.get("Title")
                or self.data.get("media_title", ""),
                "media_artist": media_info.get("Artist")
                or self.data.get("media_artist", ""),
                "media_album_name": media_info.get("Album")
                or self.data.get("media_album_name", ""),
                "media_duration": self._parse_duration(
                    media_info.get("MediaDuration")
                    or str(self.data.get("media_duration", "0")),
                ),
                "media_image_url": media_info.get("AlbumArtURI")
                or self.data.get("media_image_url", ""),
            }
            self.request_position_refresh()
            return result

        except Exception as err:
            raise UpdateFailed(f"Error fetching data from streamer: {err}") from err

    def _parse_duration(self, raw):
        if ":" in raw:
            try:
                h, m, s = (int(x) for x in raw.split(":"))
                return h * 3600 + m * 60 + s
            except ValueError:
                return 0
        return int(raw) if raw.isdigit() else 0

    def _get_local_ip(self, target_host):
        """Find local IP address used to reach target_host."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target_host, 80))
            return s.getsockname()[0]
        finally:
            s.close()

    async def async_unload(self):
        """Clean up subscriptions and stop the local server.

        The renewal loop is a config entry background task, which HA cancels.
        """
        # Unsubscribe from UPnP events
        if self._notify_watch:
            self._notify_watch()
            self._notify_watch = None
        timeout = ClientTimeout(total=5)
        if self.sid_av:
            try:
                async with self._session.request(
                    "UNSUBSCRIBE",
                    self.config_entry.data["av_transport_event_url"],
                    headers={"SID": self.sid_av},
                    timeout=timeout,
                ) as resp:
                    _LOGGER.info("Unsubscribed from AVTransport: %s", resp.status)
            except Exception:
                _LOGGER.exception("Failed to unsubscribe from AVTransport:")

        if self.sid_rc:
            try:
                async with self._session.request(
                    "UNSUBSCRIBE",
                    self.config_entry.data["rendering_control_event_url"],
                    headers={"SID": self.sid_rc},
                    timeout=timeout,
                ) as resp:
                    _LOGGER.info("Unsubscribed from RenderingControl: %s", resp.status)
            except Exception:
                _LOGGER.exception("Failed to unsubscribe from RenderingControl:")

        self.sid_av = None
        self.sid_rc = None

        # Stop local aiohttp server
        if getattr(self, "_site", None) and self._site:
            await self._site.stop()
            self._site = None
        if getattr(self, "_runner", None) and self._runner:
            await self._runner.cleanup()
            self._runner = None
