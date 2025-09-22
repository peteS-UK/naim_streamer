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

from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import (
    DOMAIN,
    CONF_BROADLINK,
    CONF_RENDERING_CONTROL_URL,
    CONF_AV_TRANSPORT_URL,
    CONF_CONNECTION_MANAGER_URL,
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
            "broadlink_remote",
            default=False,
        ): cv.boolean,
        vol.Optional(CONF_BROADLINK): EntitySelector(
            EntitySelectorConfig(
                filter={"integration": "broadlink", "domain": "remote"}
            )
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
        if user_input is not None:
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
                },
            ),
        )

    async def async_step_ssdp(self, discovery_info: dict[str, Any]) -> FlowResult:
        """Handle SSDP discovery."""

        location = discovery_info.upnp.get("ssdp_location")
        udn = discovery_info.upnp.get("UDN")
        self.friendly_name = discovery_info.upnp.get("friendlyName")
        presentation_url = discovery_info.upnp.get("presentationURL")
        self.manufacturer = discovery_info.upnp.get("manufacturer")
        self.model = discovery_info.upnp.get("model")

        # Extract host from LOCATION
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

        # Fetch and parse device description XML
        control_urls = {}
        if location:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(location) as resp:
                        xml_text = await resp.text()

                root = ET.fromstring(xml_text)
                ns = {"upnp": "urn:schemas-upnp-org:device-1-0"}

                # Find all services
                for service in root.findall(".//upnp:service", ns):
                    service_type = service.findtext(
                        "upnp:serviceType", default="", namespaces=ns
                    )
                    control_url = service.findtext(
                        "upnp:controlURL", default="", namespaces=ns
                    )

                    if service_type and control_url:
                        abs_url = urljoin(location, control_url)
                        if "RenderingControl" in service_type:
                            control_urls["rendering_control_url"] = abs_url
                        elif "AVTransport" in service_type:
                            control_urls["av_transport_url"] = abs_url
                        elif "ConnectionManager" in service_type:
                            control_urls["connection_manager_url"] = abs_url

            except Exception as e:
                # Log but don't abort discovery
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

        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Ask user to confirm adding the device."""
        if user_input is not None:
            extras = {
                CONF_RENDERING_CONTROL_URL: self.data[CONF_RENDERING_CONTROL_URL],
                CONF_AV_TRANSPORT_URL: self.data[CONF_AV_TRANSPORT_URL],
                CONF_CONNECTION_MANAGER_URL: self.data[CONF_CONNECTION_MANAGER_URL],
                "udn": self.data["udn"],
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
                },
            ),
            description_placeholders=self.context["title_placeholders"],
        )
