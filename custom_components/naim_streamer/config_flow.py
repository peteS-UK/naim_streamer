from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin, urlparse

import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import (
    ATTR_MANUFACTURER,
    CONF_HOST,
    CONF_MODEL,
    CONF_NAME,
    CONF_PORT,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from .const import (
    CONF_AV_TRANSPORT_URL,
    CONF_CONNECTION_MANAGER_URL,
    CONF_INFRARED_ENTITY_ID,
    CONF_PREAMP_IR_FRAMES,
    CONF_RENDERING_CONTROL_URL,
    CONF_STREAMER_IR_FRAMES,
    DEFAULT_IR_FRAMES,
    DOMAIN,
    MAX_IR_FRAMES,
)

_LOGGER = logging.getLogger(__name__)

NDX_SCHEMA = probatio.Schema({probatio.Required(CONF_HOST): cv.string})


CONFIG_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_NAME): cv.string,
        probatio.Required(CONF_HOST): cv.string,
        probatio.Required(CONF_PORT): cv.string,
        probatio.Required(ATTR_MANUFACTURER): cv.string,
        probatio.Required(CONF_MODEL): cv.string,
        probatio.Optional(CONF_INFRARED_ENTITY_ID): EntitySelector(
            EntitySelectorConfig(domain="infrared")
        ),
    }
)


def _default_service_urls(host: str, port: str | int) -> dict[str, str]:
    """Build the default UPnP service URLs for a streamer."""
    base = f"http://{host}:{port}"
    return {
        CONF_RENDERING_CONTROL_URL: f"{base}/RenderingControl/ctrl",
        CONF_AV_TRANSPORT_URL: f"{base}/AVTransport/ctrl",
        CONF_CONNECTION_MANAGER_URL: f"{base}/ConnectionManager/ctrl",
        "rendering_control_event_url": f"{base}/RenderingControl/evt",
        "av_transport_event_url": f"{base}/AVTransport/evt",
    }


class NaimStreamerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Naim NDX."""

    friendly_name = ""
    host = ""
    manufacturer = ""
    model = ""
    port = 8080

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow for this entry."""
        return NaimStreamerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup."""
        if user_input is not None:
            extras = _default_service_urls(user_input[CONF_HOST], user_input[CONF_PORT])
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
                },
            ),
        )

    async def async_step_ssdp(
        self, discovery_info: SsdpServiceInfo
    ) -> ConfigFlowResult:
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
                session = async_get_clientsession(self.hass)
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

    async def async_step_confirm(self, user_input=None):
        """Ask user to confirm adding the device."""
        if user_input is not None:
            extras = _default_service_urls(user_input[CONF_HOST], user_input[CONF_PORT])
            if (
                user_input[CONF_HOST] == self.data[CONF_HOST]
                and str(user_input[CONF_PORT]) == str(self.data[CONF_PORT])
            ):
                for key in extras:
                    if self.data.get(key):
                        extras[key] = self.data[key]
            extras["udn"] = self.data["udn"]

            return self.async_create_entry(
                title=self.context.get("title_placeholders", {}).get(
                    "name", "Naim Streamer"
                ),
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
            description_placeholders=self.context.get("title_placeholders"),
        )


class NaimStreamerOptionsFlow(config_entries.OptionsFlow):
    """Configure IR transmission options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the number of frames sent for each device."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.config_entry.options, **user_input}
            )

        frame_selector = NumberSelector(
            NumberSelectorConfig(min=1, max=MAX_IR_FRAMES, mode=NumberSelectorMode.BOX)
        )
        frame_count = probatio.All(
            frame_selector,
            probatio.In(range(1, MAX_IR_FRAMES + 1)),
            probatio.Coerce(int),
        )
        schema = probatio.Schema(
            {
                probatio.Required(CONF_STREAMER_IR_FRAMES): frame_count,
                probatio.Required(CONF_PREAMP_IR_FRAMES): frame_count,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_STREAMER_IR_FRAMES: self.config_entry.options.get(
                        CONF_STREAMER_IR_FRAMES, DEFAULT_IR_FRAMES
                    ),
                    CONF_PREAMP_IR_FRAMES: self.config_entry.options.get(
                        CONF_PREAMP_IR_FRAMES, DEFAULT_IR_FRAMES
                    ),
                },
            ),
        )
