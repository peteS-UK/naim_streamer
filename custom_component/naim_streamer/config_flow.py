from __future__ import annotations

from urllib.parse import urlparse, urljoin
from typing import Any
import xml.etree.ElementTree as ET

import aiohttp
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

import voluptuous as vol

import logging

_LOGGER = logging.getLogger(__name__)

NDX_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


class NaimNDXConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Naim NDX."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual setup."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=NDX_SCHEMA,
        )

    async def async_step_ssdp(self, discovery_info: dict[str, Any]) -> FlowResult:
        """Handle SSDP discovery."""

        location = discovery_info.upnp.get("ssdp_location")
        udn = discovery_info.upnp.get("UDN")
        friendly_name = discovery_info.upnp.get("friendlyName")
        presentation_url = discovery_info.upnp.get("presentationURL")

        # Extract host from LOCATION
        host = None
        if location:
            parsed = urlparse(location)
            host = parsed.hostname
        elif presentation_url:
            parsed = urlparse(presentation_url)
            host = parsed.hostname
            location = f"http://{host}:8080/description.xml"

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
                _LOGGER.critical("Failed to fetch/parse NDX description: %s", e)

        self.context["title_placeholders"] = {
            "name": friendly_name or host or "Naim NDX"
        }

        self.data = {
            CONF_HOST: host,
            "udn": udn,
            "friendly_name": friendly_name,
            **control_urls,
        }

        # Create config entry with all details
        # return self.async_create_entry(
        #    title=friendly_name or host or "Naim NDX",
        #    data={
        #        CONF_HOST: host,
        #        "udn": udn,
        #        "friendly_name": friendly_name,
        #        **control_urls,
        #    },
        # )

        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Ask user to confirm adding the device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"],
                data=self.data,
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=self.context["title_placeholders"],
        )
