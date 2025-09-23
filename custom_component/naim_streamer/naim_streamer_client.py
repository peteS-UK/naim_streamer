import aiohttp
import logging
from typing import Optional

import xml.etree.ElementTree as ET

import mimetypes
from urllib.parse import urlparse

from homeassistant.components.media_player import (
    MediaPlayerState,
)


_LOGGER = logging.getLogger(__name__)


class NaimStreamerClient:
    """Async SOAP client & IR for Naim Streamers."""

    def __init__(
        self,
        name: str,
        udn: str,
        manufacturer: str,
        model: str,
        port: int,
        rendering_control_url: str,
        av_transport_url: str,
        connection_manager_url: str,
        host: str = None,
    ):
        self._name = name
        self._udn = udn
        self._manufacturer = manufacturer
        self._model = model
        self._port = port
        self._rendering_control_url = rendering_control_url
        self._av_transport_url = av_transport_url
        self._connection_manager_url = connection_manager_url
        self.host = host
        self.last_uri = None
        self.last_metadata = None
        self.state = MediaPlayerState.IDLE
        self.status = ""

    async def subscribe_service(
        self, event_url: str, callback_url: str, timeout: int = 300
    ) -> str:
        """
        Subscribe to a UPnP event service.

        :param event_url: Absolute eventSubURL for the service (e.g. http://host:port/AVTransport/evt)
        :param callback_url: Absolute URL of our local NOTIFY handler
        :param timeout: Subscription timeout in seconds (default 300)
        :return: SID string from the device
        """
        headers = {
            "CALLBACK": f"<{callback_url}>",
            "NT": "upnp:event",
            "TIMEOUT": f"Second-{timeout}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.request("SUBSCRIBE", event_url, headers=headers) as resp:
                _LOGGER.debug(
                    "SUBSCRIBE %s returned %s headers=%s",
                    event_url,
                    resp.status,
                    resp.headers,
                )
                if resp.status != 200:
                    raise Exception(f"SUBSCRIBE failed ({resp.status}) for {event_url}")
                sid = resp.headers.get("SID")
                if not sid:
                    raise Exception(f"No SID returned for {event_url}")
                _LOGGER.debug("Subscribed to %s with SID %s", event_url, sid)
                return sid

    async def renew_subscription(
        self, event_url: str, sid: str, timeout: int = 300
    ) -> str:
        """
        Renew an existing UPnP event subscription.

        :param event_url: Absolute eventSubURL for the service
        :param sid: Subscription ID to renew
        :param timeout: Subscription timeout in seconds
        :return: New SID (may be same as old)
        """
        headers = {
            "SID": sid,
            "TIMEOUT": f"Second-{timeout}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.request("SUBSCRIBE", event_url, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception(f"Renew failed ({resp.status}) for {event_url}")
                new_sid = resp.headers.get("SID", sid)
                _LOGGER.debug("Renewed subscription %s -> %s", sid, new_sid)
                return new_sid

    async def has_current_uri(self) -> bool:
        """Return True if the transport has a non-empty CurrentURI."""
        info = await self.get_media_info(parsed=True)
        return bool(info.get("CurrentURI"))

    async def seek(self, position_seconds: int, parsed: bool = False):
        """Seek to a position in the current track."""
        hours = position_seconds // 3600
        minutes = (position_seconds % 3600) // 60
        seconds = position_seconds % 60
        target = f"{hours:02}:{minutes:02}:{seconds:02}"

        _LOGGER.debug("Seeking to %s (REL_TIME)", target)
        raw = await self._soap_request(
            service="AVTransport",
            action="Seek",
            arguments={
                "InstanceID": 0,
                "Unit": "REL_TIME",
                "Target": target,
            },
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def seekold(
        self,
        instance_id: int = 0,
        unit: str = "REL_TIME",
        target: str = "00:00:00",
        parsed: bool = False,
    ):
        body = f"""
<u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
  <Unit>{unit}</Unit>
  <Target>{target}</Target>
</u:Seek>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Seek",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def play_url(
        self,
        uri: str,
        title: str = "",
        artist: str = "",
        album: str = "",
        album_art: str = "",
    ):
        """Set the transport to a given URL and start playback."""
        # Guess protocolInfo from extension or MIME type
        mime_type, _ = mimetypes.guess_type(uri)
        if not mime_type:
            # Fallback for common stream types
            if uri.lower().endswith(".aac") or "stationstream" in uri:
                mime_type = "audio/x-mpeg-aac"
            elif uri.lower().endswith(".mp3"):
                mime_type = "audio/mpeg"
            elif uri.lower().endswith(".flac"):
                mime_type = "audio/x-flac"
            else:
                mime_type = "*/*"

        protocol_info = f"http-get:*:{mime_type}:*"

        # Auto-fill title from filename if not provided
        if not title:
            path = urlparse(uri).path
            title = path.split("/")[-1] or "Unknown"

        # Build minimal DIDL-Lite metadata
        didl = f"""<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
            xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
            <item>
                <dc:title>{title}</dc:title>
                {"<upnp:artist>" + artist + "</upnp:artist>" if artist else ""}
                {"<upnp:album>" + album + "</upnp:album>" if album else ""}
                {"<upnp:albumArtURI>" + album_art + "</upnp:albumArtURI>" if album_art else ""}
                <res protocolInfo="{protocol_info}">{uri}</res>
            </item>
        </DIDL-Lite>"""

        _LOGGER.debug("Setting AVTransport URI to %s with metadata:\n%s", uri, didl)
        await self.set_av_transport_uri(uri, didl)
        await self.play()

        # Persist for resume
        self.last_uri = uri
        self.last_metadata = didl

    @property
    def name(self):
        return self._name

    @property
    def udn(self):
        return self._udn

    @property
    def manufacturer(self):
        return self._manufacturer

    @property
    def model(self):
        return self._model

    @property
    def port(self):
        return self._port

    @staticmethod
    def parse_soap_response(xml_string: str, tags: list[str]) -> dict[str, str]:
        """Parse SOAP XML and extract values for given tags (namespace-agnostic)."""
        result: dict[str, str] = {}
        try:
            root = ET.fromstring(xml_string.strip())
            for elem in root.iter():
                tag_name = elem.tag.split("}")[-1]
                if tag_name in tags:
                    result[tag_name] = elem.text or ""
        except ET.ParseError as e:
            _LOGGER.error("Failed to parse SOAP XML: %s", e)
        except Exception as e:
            _LOGGER.error("Error extracting tags %s: %s", tags, e)
        return result

    async def _soap_request(
        self, url: str, service: str, action: str, body_xml: str
    ) -> Optional[str]:
        """Send a SOAP request and return the raw XML response."""
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{service}#{action}"',
        }
        envelope = f"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    {body_xml}
  </s:Body>
</s:Envelope>"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, data=envelope.encode("utf-8"), headers=headers
                ) as resp:
                    resp.raise_for_status()
                    return await resp.text()
        except Exception as e:
            _LOGGER.error("SOAP request %s failed: %s", action, e)
            return None

    # ---------------- RenderingControl ----------------
    async def get_mute(
        self, instance_id: int = 0, channel: str = "Master", parsed: bool = True
    ):
        raw = await self._soap_request(
            self._rendering_control_url,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "GetMute",
            f"""<u:GetMute xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
                  <InstanceID>{instance_id}</InstanceID>
                  <Channel>{channel}</Channel>
                </u:GetMute>""",
        )
        return self.parse_soap_response(raw, ["CurrentMute"]) if parsed and raw else raw

    async def get_volume(
        self, instance_id: int = 0, channel: str = "Master", parsed: bool = True
    ):
        raw = await self._soap_request(
            self._rendering_control_url,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "GetVolume",
            f"""<u:GetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
                  <InstanceID>{instance_id}</InstanceID>
                  <Channel>{channel}</Channel>
                </u:GetVolume>""",
        )
        return (
            self.parse_soap_response(raw, ["CurrentVolume"]) if parsed and raw else raw
        )

    async def set_mute(
        self,
        desired_mute: bool,
        instance_id: int = 0,
        channel: str = "Master",
        parsed: bool = False,
    ):
        body = f"""
<u:SetMute xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
  <InstanceID>{instance_id}</InstanceID>
  <Channel>{channel}</Channel>
  <DesiredMute>{"1" if desired_mute else "0"}</DesiredMute>
</u:SetMute>"""
        raw = await self._soap_request(
            self._rendering_control_url,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "SetMute",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def set_volume(
        self,
        volume: int,
        instance_id: int = 0,
        channel: str = "Master",
        parsed: bool = False,
    ):
        body = f"""
<u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
  <InstanceID>{instance_id}</InstanceID>
  <Channel>{channel}</Channel>
  <DesiredVolume>{volume}</DesiredVolume>
</u:SetVolume>"""
        raw = await self._soap_request(
            self._rendering_control_url,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "SetVolume",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def set_av_transport_uri(
        self, uri: str, instance_id: int = 0, metadata: str = "", parsed: bool = False
    ):
        body = f"""
<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
  <CurrentURI>{uri}</CurrentURI>
  <CurrentURIMetaData>{metadata}</CurrentURIMetaData>
</u:SetAVTransportURI>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "SetAVTransportURI",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def set_next_av_transport_uri(
        self, uri: str, instance_id: int = 0, metadata: str = "", parsed: bool = False
    ):
        body = f"""
<u:SetNextAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
  <NextURI>{uri}</NextURI>
  <NextURIMetaData>{metadata}</NextURIMetaData>
</u:SetNextAVTransportURI>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "SetNextAVTransportURI",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def play(self, instance_id: int = 0, speed: str = "1", parsed: bool = False):
        body = f"""
<u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
  <Speed>{speed}</Speed>
</u:Play>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Play",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def stop(self, instance_id: int = 0, parsed: bool = False):
        body = f"""
<u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
</u:Stop>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Stop",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def pause(self, instance_id: int = 0, parsed: bool = False):
        body = f"""
<u:Pause xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
</u:Pause>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Pause",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def next(self, instance_id: int = 0, parsed: bool = False):
        body = f"""
<u:Next xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
</u:Next>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Next",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def previous(self, instance_id: int = 0, parsed: bool = False):
        body = f"""
<u:Previous xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
</u:Previous>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Previous",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    async def set_play_mode(
        self, instance_id: int = 0, play_mode: str = "NORMAL", parsed: bool = False
    ):
        body = f"""
<u:SetPlayMode xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>{instance_id}</InstanceID>
  <NewPlayMode>{play_mode}</NewPlayMode>
</u:SetPlayMode>"""
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "SetPlayMode",
            body,
        )
        return {"success": bool(raw and "Fault" not in raw)} if parsed else raw

    # ---------------- AVTransport ----------------

    async def get_media_info(self, instance_id: int = 0, parsed: bool = True):
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "GetMediaInfo",
            f"""<u:GetMediaInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                  <InstanceID>{instance_id}</InstanceID>
                </u:GetMediaInfo>""",
        )
        tags = [
            "NrTracks",
            "MediaDuration",
            "CurrentURI",
            "CurrentURIMetaData",
            "NextURI",
            "NextURIMetaData",
            "PlayMedium",
            "RecordMedium",
            "WriteStatus",
        ]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    async def get_transport_info(self, instance_id: int = 0, parsed: bool = True):
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "GetTransportInfo",
            f"""<u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                  <InstanceID>{instance_id}</InstanceID>
                </u:GetTransportInfo>""",
        )
        tags = ["CurrentTransportState", "CurrentTransportStatus", "CurrentSpeed"]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    async def get_position_info(self, instance_id: int = 0, parsed: bool = True):
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "GetPositionInfo",
            f"""<u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                  <InstanceID>{instance_id}</InstanceID>
                </u:GetPositionInfo>""",
        )
        tags = [
            "Track",
            "TrackDuration",
            "TrackMetaData",
            "TrackURI",
            "RelTime",
            "AbsTime",
            "RelCount",
            "AbsCount",
        ]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    async def get_device_capabilities(self, instance_id: int = 0, parsed: bool = True):
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "GetDeviceCapabilities",
            f"""<u:GetDeviceCapabilities xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                  <InstanceID>{instance_id}</InstanceID>
                </u:GetDeviceCapabilities>""",
        )
        tags = ["PlayMedia", "RecMedia", "RecQualityModes"]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    async def get_transport_settings(self, instance_id: int = 0, parsed: bool = True):
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "GetTransportSettings",
            f"""<u:GetTransportSettings xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                  <InstanceID>{instance_id}</InstanceID>
                </u:GetTransportSettings>""",
        )
        tags = ["PlayMode", "RecQualityMode"]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    async def get_current_transport_actions(
        self, instance_id: int = 0, parsed: bool = True
    ):
        raw = await self._soap_request(
            self._av_transport_url,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "GetCurrentTransportActions",
            f"""<u:GetCurrentTransportActions xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
                  <InstanceID>{instance_id}</InstanceID>
                </u:GetCurrentTransportActions>""",
        )
        tags = ["Actions"]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    # ---------------- ConnectionManager ----------------

    async def get_protocol_info(self, parsed: bool = True):
        raw = await self._soap_request(
            self._connection_manager_url,
            "urn:schemas-upnp-org:service:ConnectionManager:1",
            "GetProtocolInfo",
            '<u:GetProtocolInfo xmlns:u="urn:schemas-upnp-org:service:ConnectionManager:1"/>',
        )
        tags = ["Source", "Sink"]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    async def get_current_connection_ids(self, parsed: bool = True):
        raw = await self._soap_request(
            self._connection_manager_url,
            "urn:schemas-upnp-org:service:ConnectionManager:1",
            "GetCurrentConnectionIDs",
            '<u:GetCurrentConnectionIDs xmlns:u="urn:schemas-upnp-org:service:ConnectionManager:1"/>',
        )
        tags = ["ConnectionIDs"]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw

    async def get_current_connection_info(
        self, connection_id: int, parsed: bool = True
    ):
        raw = await self._soap_request(
            self._connection_manager_url,
            "urn:schemas-upnp-org:service:ConnectionManager:1",
            "GetCurrentConnectionInfo",
            f"""<u:GetCurrentConnectionInfo xmlns:u="urn:schemas-upnp-org:service:ConnectionManager:1">
                   <ConnectionID>{connection_id}</ConnectionID>
                </u:GetCurrentConnectionInfo>""",
        )
        tags = [
            "RcsID",
            "AVTransportID",
            "ProtocolInfo",
            "PeerConnectionManager",
            "PeerConnectionID",
            "Direction",
            "Status",
        ]
        return self.parse_soap_response(raw, tags) if parsed and raw else raw
