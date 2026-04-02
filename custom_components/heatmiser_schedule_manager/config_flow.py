"""Config flow for Heatmiser Schedule Manager."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

HEATMISERNEO_DOMAIN = "heatmiserneo"


class HeatmiserScheduleManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Heatmiser Schedule Manager."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        neo_entries = self.hass.config_entries.async_entries(HEATMISERNEO_DOMAIN)

        if not neo_entries:
            return self.async_abort(reason="heatmiserneo_not_configured")

        if user_input is not None:
            if len(neo_entries) > 1:
                neo_entry_id = user_input["hub"]
                neo_entry = self.hass.config_entries.async_get_entry(neo_entry_id)
            else:
                neo_entry = neo_entries[0]

            await self.async_set_unique_id(f"hsm_{neo_entry.entry_id}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Schedule Manager ({neo_entry.title})",
                data={"heatmiserneo_entry_id": neo_entry.entry_id},
            )

        if len(neo_entries) > 1:
            data_schema = vol.Schema(
                {
                    vol.Required("hub"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": e.entry_id, "label": e.title}
                                for e in neo_entries
                            ]
                        )
                    )
                }
            )
        else:
            data_schema = vol.Schema({})

        return self.async_show_form(step_id="user", data_schema=data_schema)
