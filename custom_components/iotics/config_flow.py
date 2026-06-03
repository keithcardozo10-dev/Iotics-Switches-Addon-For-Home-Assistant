"""Config flow for Iotics Smart Home integration."""
from __future__ import annotations
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .iotics_api import IoticsApiClient, IOTICS_APPID_DEFAULT

_LOGGER = logging.getLogger(__name__)

DOMAIN = "iotics"

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_EMAIL): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Optional("appid", default=IOTICS_APPID_DEFAULT): str,
})


class IoticsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Iotics."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            appid = user_input.get("appid", IOTICS_APPID_DEFAULT)

            # Test connection
            api = IoticsApiClient(email, password, appid)
            session = await self.hass.async_add_executor_job(api.login)
            if session:
                return self.async_create_entry(
                    title=f"Iotics ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        "appid": appid,
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle re-authentication (token expired)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Re-auth form."""
        errors = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            appid = user_input.get("appid", IOTICS_APPID_DEFAULT)

            api = IoticsApiClient(email, password, appid)
            session = await self.hass.async_add_executor_job(api.login)
            if session:
                existing_entry = self._get_reauth_entry()
                self.hass.config_entries.async_update_entry(
                    existing_entry,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        "appid": appid,
                    },
                )
                await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
