from .naim_ndx_client import NaimNDXClient

import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    data = entry.data

    _LOGGER.critical("Data %s", data)
    client = NaimNDXClient(
        rendering_control_url=data["rendering_control_url"],
        av_transport_url=data["av_transport_url"],
        connection_manager_url=data["connection_manager_url"],
    )

    # Example: log current mute state
    mute_state = await client.get_mute()
    _LOGGER.critical("NDX mute state: %s", mute_state)

    hass.data.setdefault("naim_ndx", {})[entry.entry_id] = client
    return True
