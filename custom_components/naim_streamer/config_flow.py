from __future__ import annotations

from urllib.parse import urlparse, urljoin
from typing import Any
import xml.etree.ElementTree as ET

import aiohttp
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    ATTR_MANUFACTURER,
    CONF_MODEL,
    CONF_PORT,
)
from homeassistant.data_entry_flow import FlowResult

from homeassistant.helpers import config_validation as cv

from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    DOMAIN,
    CONF_REMOTE_ENTITY,
    CONF_RENDERING_CONTROL_URL,
    CONF_AV_TRANSPORT_URL,
    CONF_CONNECTION_MANAGER_URL,
    CONF_BROADLINK_REMOTE,
    CONF_REMOTE_TYPE,
)


import voluptuous as vol

import logging

_LOGGER = logging.getLogger(__name__)

NDX_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.string,
        vol.Required(ATTR_MANUFACTURER): cv.string,
        vol.Required(CONF_MODEL): cv.string,
        vol.Optional(
            CONF_BROADLINK_REMOTE,
            default=False,
        ): cv.boolean,
        vol.Required(CONF_REMOTE_TYPE): SelectSelector(
            SelectSelectorConfig(options=["None", "Broadlink", "Tuya"])
        ),
        vol.Optional(CONF_REMOTE_ENTITY): EntitySelector(
            EntitySelectorConfig(filter={"domain": "remote"})
        ),
    }
)


class NaimStreamerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Naim NDX."""

    friendly_name = ""
    host = ""
    manufacturer = ""
    model = ""
    port = 8080

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.validate_remote(user_input)
            except ValueError:
                errors["base"] = "data"
            if not errors:
                extras = {}
                extras[CONF_RENDERING_CONTROL_URL] = (
                    f"http://{user_input[CONF_HOST]}:{user_input[CONF_PORT]}/RenderingControl/ctrl"
                )
                extras[CONF_AV_TRANSPORT_URL] = (
                    f"http://{user_input[CONF_HOST]}:{user_input[CONF_PORT]}/AVTransport/ctrl"
                )
                extras[CONF_CONNECTION_MANAGER_URL] = (
                    f"http://{user_input[CONF_HOST]}:{user_input[CONF_PORT]}/ConnectionManager/ctrl"
                )
                extras["udn"] = (
                    "naim_streamer_"
                    + user_input[CONF_NAME].replace(" ", "_").replace("-", "_").lower()
                )
                extras["rendering_control_event_url"] = (
                    f"http://{user_input[CONF_HOST]}:{user_input[CONF_PORT]}//RenderingControl/evt"
                )
                extras["av_transport_event_url"] = (
                    f"http://{user_input[CONF_HOST]}:{user_input[CONF_PORT]}//AVTransport/evt"
                )
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input | extras
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                CONFIG_SCHEMA,
                {
                    CONF_NAME: self.friendly_name or "Naim Streamer",
                    CONF_HOST: self.host,
                    CONF_PORT: self.port or 8080,
                    ATTR_MANUFACTURER: self.manufacturer or "Naim Audio Ltd.",
                    CONF_MODEL: self.model or "NDX",
                    "broadlink_remote": False,
                    CONF_REMOTE_TYPE: "None",
                },
            ),
            errors=errors,
        )

    async def async_step_ssdp(self, discovery_info: dict[str, Any]) -> FlowResult:
        """Handle SSDP discovery."""

        location = discovery_info.upnp.get("ssdp_location")
        udn = discovery_info.upnp.get("UDN")
        self.friendly_name = discovery_info.upnp.get("friendlyName")
        presentation_url = discovery_info.upnp.get("presentationURL")
        self.manufacturer = discovery_info.upnp.get("manufacturer")
        self.model = discovery_info.upnp.get("model")

        # Extract host from LOCATION or presentationURL
        self.host = None
        if location:
            parsed = urlparse(location)
            self.host = parsed.hostname
        elif presentation_url:
            parsed = urlparse(presentation_url)
            self.host = parsed.hostname
            location = f"http://{self.host}:{self.port}/description.xml"

        # Set unique ID to avoid duplicates
        await self.async_set_unique_id(udn)
        self._abort_if_unique_id_configured()

        control_urls: dict[str, str] = {}
        if location:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(location) as resp:
                        xml_text = await resp.text()

                root = ET.fromstring(xml_text)
                ns = {"upnp": "urn:schemas-upnp-org:device-1-0"}

                for service in root.findall(".//upnp:service", ns):
                    service_type = service.findtext(
                        "upnp:serviceType", default="", namespaces=ns
                    )
                    control_url = service.findtext(
                        "upnp:controlURL", default="", namespaces=ns
                    )
                    event_url = service.findtext(
                        "upnp:eventSubURL", default="", namespaces=ns
                    )

                    _LOGGER.debug(
                        "Found service: %s controlURL=%s eventSubURL=%s",
                        service_type,
                        control_url,
                        event_url,
                    )

                    if service_type and control_url:
                        abs_ctrl_url = urljoin(location, control_url)
                        abs_event_url = (
                            urljoin(location, event_url) if event_url else None
                        )

                        if "RenderingControl" in service_type:
                            control_urls["rendering_control_url"] = abs_ctrl_url
                            if abs_event_url:
                                control_urls["rendering_control_event_url"] = (
                                    abs_event_url
                                )
                        elif "AVTransport" in service_type:
                            control_urls["av_transport_url"] = abs_ctrl_url
                            if abs_event_url:
                                control_urls["av_transport_event_url"] = abs_event_url
                        elif "ConnectionManager" in service_type:
                            control_urls["connection_manager_url"] = abs_ctrl_url

            except Exception as e:
                _LOGGER.critical("Failed to fetch/parse streamer description: %s", e)

        self.context["title_placeholders"] = {
            "name": self.friendly_name or self.host or "Naim Streamer"
        }

        self.data = {
            CONF_NAME: self.friendly_name or "Naim Streamer",
            CONF_HOST: self.host,
            "udn": udn,
            "friendly_name": self.friendly_name,
            ATTR_MANUFACTURER: self.manufacturer,
            CONF_MODEL: self.model,
            CONF_PORT: self.port,
            **control_urls,
        }

        _LOGGER.debug("SSDP discovery data prepared: %s", self.data)

        return await self.async_step_confirm()

    async def validate_remote(self, data: dict) -> None:
        if CONF_REMOTE_TYPE not in data.keys():
            data[CONF_REMOTE_TYPE] = "None"

        if CONF_REMOTE_ENTITY not in data.keys():
            data[CONF_REMOTE_ENTITY] = ""

        if (len(data[CONF_REMOTE_ENTITY]) < 2) and (data[CONF_REMOTE_TYPE != "None"]):
            # Manual entry requires host and name
            raise ValueError

    async def async_step_confirm(self, user_input=None):
        """Ask user to confirm adding the device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.validate_remote(user_input)
            except ValueError:
                errors["base"] = "data"
            if not errors:
                # Input is valid, set data.
                extras = {
                    CONF_RENDERING_CONTROL_URL: self.data[CONF_RENDERING_CONTROL_URL],
                    CONF_AV_TRANSPORT_URL: self.data[CONF_AV_TRANSPORT_URL],
                    CONF_CONNECTION_MANAGER_URL: self.data[CONF_CONNECTION_MANAGER_URL],
                    "udn": self.data["udn"],
                    "rendering_control_event_url": self.data.get(
                        "rendering_control_event_url"
                    ),
                    "av_transport_event_url": self.data.get("av_transport_event_url"),
                }

                return self.async_create_entry(
                    title=self.context["title_placeholders"]["name"],
                    data=user_input | extras,
                )

        return self.async_show_form(
            step_id="confirm",
            data_schema=self.add_suggested_values_to_schema(
                CONFIG_SCHEMA,
                {
                    CONF_NAME: self.friendly_name or "Naim Streamer",
                    CONF_HOST: self.host,
                    CONF_PORT: self.port or 8080,
                    ATTR_MANUFACTURER: self.manufacturer or "Naim Audio Ltd.",
                    CONF_MODEL: self.model or "NDX",
                    CONF_REMOTE_TYPE: "None",
                },
            ),
            description_placeholders=self.context["title_placeholders"],
            errors=errors,
        )
