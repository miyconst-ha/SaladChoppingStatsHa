"""Setup and reauthentication for Salad Chopping."""

import voluptuous as vol
from aiohttp import DummyCookieJar

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import SaladAuthError, SaladClient, SaladError
from .const import CONF_ACKNOWLEDGE_RISKS, CONF_AUTH_COOKIE, DOMAIN

COOKIE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AUTH_COOKIE): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_ACKNOWLEDGE_RISKS, default=False): bool,
    }
)


class SaladConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a Salad dashboard account."""

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Validate credentials and add the account."""
        return await self._async_cookie_step("user", user_input)

    async def async_step_reauth(self, entry_data) -> ConfigFlowResult:
        """Start reauthentication after Salad rejects the session."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        """Replace the expired cookie for the same account."""
        return await self._async_cookie_step("reauth_confirm", user_input)

    async def _async_cookie_step(self, step_id, user_input) -> ConfigFlowResult:
        errors = {}
        if user_input is not None and user_input.get(CONF_ACKNOWLEDGE_RISKS) is not True:
            # A required boolean can still be false. Enforce explicit consent
            # before opening a session or sending the cookie to Salad.
            return self.async_show_form(
                step_id=step_id,
                data_schema=COOKIE_SCHEMA,
                errors={CONF_ACKNOWLEDGE_RISKS: "acknowledgement_required"},
            )
        if user_input is not None:
            cookie = user_input[CONF_AUTH_COOKIE].strip()
            session = async_create_clientsession(
                self.hass, auto_cleanup=False, cookie_jar=DummyCookieJar()
            )
            try:
                client = SaladClient(session, cookie)
                account_id = await client.account_id()
                await client.earnings()
            except SaladAuthError:
                errors["base"] = "invalid_auth"
            except SaladError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(account_id)
                data = {CONF_AUTH_COOKIE: cookie}
                if step_id == "reauth_confirm":
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=data
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Salad Chopping", data=data)
            finally:
                session.detach()

        return self.async_show_form(step_id=step_id, data_schema=COOKIE_SCHEMA, errors=errors)
