import aiohttp
import logging
from typing import Optional

import xml.etree.ElementTree as ET


_LOGGER = logging.getLogger(__name__)


class NaimNDXClient:
    """Async SOAP client for Naim NDX RenderingControl + AVTransport + ConnectionManager."""

    def __init__(
        self,
        rendering_control_url: str,
        av_transport_url: str,
        connection_manager_url: str,
    ):
        self._rendering_control_url = rendering_control_url
        self._av_transport_url = av_transport_url
        self._connection_manager_url = connection_manager_url

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
