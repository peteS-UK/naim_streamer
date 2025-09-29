import logging
import socket
import asyncio
import html
import re

from lxml import etree

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta
from aiohttp import web

from urllib.parse import urljoin

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, ATTR_MANUFACTURER, CONF_MODEL, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components.media_player import MediaPlayerState

from homeassistant.exceptions import ServiceValidationError

from .naim_streamer_client import NaimStreamerClient

from aiohttp import ClientSession

from .const import (
    BROADLINK_COMMANDS,
    TUYA_COMMANDS,
    CONF_REMOTE_ENTITY,
    CONF_REMOTE_TYPE,
)

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
        self.streamer = None
        self.sid_av = None
        self.sid_rc = None
        self._runner = None
        self._site = None
        self.data = {}
        self.remote_entity = config_entry.data.get(CONF_REMOTE_ENTITY)
        self.remote_type = config_entry.data.get(CONF_REMOTE_TYPE)

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
        elif self.remote_entity:
            await self._send_remote_command(command)
        else:
            raise ServiceValidationError(
                f"{command} is only supported with a remote entity"
            )

    async def _send_remote_command(self, command):
        if self.remote_type == "Tuya RC5":
            await self.hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self.remote_entity,
                    "num_repeats": "1",
                    "delay_secs": "0.4",
                    "command": f"{TUYA_COMMANDS[command]['rc5']}",
                },
            )
        if self.remote_type == "Tuya Raw":
            await self.hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self.remote_entity,
                    "num_repeats": "1",
                    "delay_secs": "0.4",
                    "command": f"{TUYA_COMMANDS[command]['raw']}",
                },
            )

        if self.remote_type == "Broadlink":
            await self.hass.services.async_call(
                "remote",
                "send_command",
                {
                    "entity_id": self.remote_entity,
                    "num_repeats": "1",
                    "delay_secs": "0.4",
                    "command": f"b64:{BROADLINK_COMMANDS[command]}",
                },
            )

    async def async_play(self):
        if self.remote_entity:
            await self._send_remote_command("play")
        else:
            if not self.streamer.last_uri or self.streamer.status == "ERROR_OCCURRED":
                uri = self.data.get("media_uri") or self.streamer.last_uri
                metadata = (
                    self.data.get("media_metadata") or self.streamer.last_metadata
                )

                if uri and metadata:
                    _LOGGER.debug("Restoring AVTransport URI before play: %s", uri)
                    await self.streamer.set_av_transport_uri(uri, metadata)
                else:
                    _LOGGER.warning("No stored URI/metadata to restore before play")

            await self.streamer.play()

    async def async_pause(self):
        """Pause and confirm."""
        if self.remote_entity:
            await self._send_remote_command("pause")
        else:
            await self.streamer.pause()

    async def async_volume_up(self):
        """Pause and confirm."""
        if self.remote_entity:
            await self._send_remote_command("vol+")

    async def async_volume_down(self):
        """Pause and confirm."""
        if self.remote_entity:
            await self._send_remote_command("vol-")

    async def async_mute_toggle(self):
        """Pause and confirm."""
        if self.remote_entity:
            await self._send_remote_command("mute")

    async def async_stop(self):
        """Stop and confirm."""
        if self.remote_entity:
            await self._send_remote_command("stop")
        else:
            await self.streamer.stop()

    async def async_next_track(self):
        """Skip to the next track and confirm actual state."""
        if self.remote_entity:
            await self._send_remote_command("next")
        else:
            await self.streamer.next()

    async def async_previous_track(self):
        """Skip to the previous track and confirm actual state."""
        if self.remote_entity:
            await self._send_remote_command("previous")
        else:
            await self.streamer.previous()

    async def _async_setup(self):
        """Initialise client and subscribe to events."""
        self.streamer = NaimStreamerClient(
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
        self.uuid = self.streamer.udn

        # Start local aiohttp server for NOTIFY callbacks
        app = web.Application()
        app.router.add_route("NOTIFY", "/upnp/event", self._handle_notify)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", 0)
        await self._site.start()
        port = self._site._server.sockets[0].getsockname()[1]
        local_ip = self._get_local_ip(self.streamer.host)

        callback_url = f"http://{local_ip}:{port}/upnp/event"

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
                # Both subscriptions healthy — go push‑only
                self.update_interval = None
            self._renew_task = asyncio.create_task(self._renew_loop(callback_url))
        except Exception as err:
            _LOGGER.warning("Subscription failed, using fast poll: %s", err)
            self.update_interval = timedelta(seconds=30)

        _LOGGER.debug("AVTransport SID: %s", self.sid_av)
        _LOGGER.debug("RenderingControl SID: %s", self.sid_rc)

        return await self._async_update_data()

    async def _renew_loop(self, callback_url: str):
        timeout = 300
        renew_interval = timeout - 60
        try:
            while True:
                await asyncio.sleep(renew_interval)
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
                    if self.sid_av and self.sid_rc:
                        # Both healthy — push‑only
                        self.update_interval = None
                    else:
                        # One missing — fast poll
                        self.update_interval = timedelta(seconds=30)
                except Exception as err:
                    _LOGGER.warning("Renewal failed: %s", err)
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
                        if self.sid_av and self.sid_rc:
                            self.update_interval = None
                        else:
                            self.update_interval = timedelta(seconds=30)
                    except Exception as err2:
                        _LOGGER.error("Re‑subscribe failed: %s", err2)
                        self.update_interval = timedelta(seconds=30)
        except asyncio.CancelledError:
            _LOGGER.debug("Renewal loop cancelled")
            raise

    async def _handle_notify(self, request):
        body = await request.text()
        _LOGGER.debug("Received from %s NOTIFY:\n%s", request.remote, body)

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
            for prop in root.findall(".//e:property", ns):
                for child in prop:
                    if child.tag == "LastChange" and (child.text or "").strip():
                        self._parse_last_change(child.text)

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

            raw_state = transport_data.get("CurrentTransportState", "UNKNOWN").upper()

            return {
                "volume": int(
                    vol_data.get("CurrentVolume", self.data.get("volume", 0))
                ),
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
        """Clean up subscriptions, stop renewal loop, and stop local server."""
        # Cancel renewal loop if running
        if (
            hasattr(self, "_renew_task")
            and self._renew_task
            and not self._renew_task.done()
        ):
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass

        # Unsubscribe from UPnP events
        async with ClientSession() as session:
            if self.sid_av:
                try:
                    async with session.request(
                        "UNSUBSCRIBE",
                        self.config_entry.data["av_transport_event_url"],
                        headers={"SID": self.sid_av},
                    ) as resp:
                        _LOGGER.info("Unsubscribed from AVTransport: %s", resp.status)
                except Exception as e:
                    _LOGGER.warning("Failed to unsubscribe from AVTransport: %s", e)

            if self.sid_rc:
                try:
                    async with session.request(
                        "UNSUBSCRIBE",
                        self.config_entry.data["rendering_control_event_url"],
                        headers={"SID": self.sid_rc},
                    ) as resp:
                        _LOGGER.info(
                            "Unsubscribed from RenderingControl: %s", resp.status
                        )
                except Exception as e:
                    _LOGGER.warning(
                        "Failed to unsubscribe from RenderingControl: %s", e
                    )

        self.sid_av = None
        self.sid_rc = None

        # Stop local aiohttp server
        if getattr(self, "_site", None):
            await self._site.stop()
            self._site = None
        if getattr(self, "_runner", None):
            await self._runner.cleanup()
            self._runner = None
