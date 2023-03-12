from collections import OrderedDict
import logging

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import CONF_COUNTER_ID, CONF_PROVIDER, DOMAIN
from .pysuez1 import SuezClient

_LOGGER = logging.getLogger(__name__)


def schema(defaults=None):
    """
    Build the schema.

    There are (at least now) four parameters:
    - counter id
    - username (email address)
    - password
    - provider, can be chosen from the list that SuezClient gives

    defaults for all the parameters are taken from the `defaults`
    """
    source = defaults or dict()
    sch = OrderedDict()
    sch[vol.Required(CONF_COUNTER_ID, default=source.get(CONF_COUNTER_ID, ""))] = cv.string
    sch[vol.Required(CONF_USERNAME, default=source.get(CONF_USERNAME, "user@example.org"))] = cv.string
    sch[vol.Required(CONF_PASSWORD, default=source.get(CONF_PASSWORD, ""))] = cv.string
    sch[vol.Optional(CONF_PROVIDER, default=source.get(CONF_PROVIDER, None))] = vol.In(SuezClient.providers())
    return vol.Schema(sch)


class SuezOptionsFlow(OptionsFlow):

    def __init__(self, config_entry) -> None:
        """
        Initialize options flow
        """
        self.config_entry = config_entry
        _LOGGER.debug(f"optionsflow::__init__: {config_entry.options=}")
        _LOGGER.debug(f"optionsflow::__init__: {config_entry.data=}")
        self.defaults = {**config_entry.data, **config_entry.options}

    async def async_step_init(self, info):
        """
        Manage the options
        """
        if info is not None:
            _LOGGER.debug(f"optionsflow::async_step_init: {info=}")
            return self.async_create_entry(title="toutsurmoneau", data=info)

        return self.async_show_form(
            step_id="init",
            data_schema=schema(self.defaults)
        )


class SuezConfigFlow(ConfigFlow, domain=DOMAIN):

    async def async_step_user(self, info=None):
        """
        first step in the configuration
        """
        _LOGGER.debug(f'configflow::step_user: {info=}')
        if self._async_current_entries():
            _LOGGER.error("configflow::step_user: already configured")
            return self.async_abort(reason="single_instance_allowed")
        await self.async_set_unique_id(DOMAIN)
        return await self.async_step_configure(info)

    async def async_step_configure(self, info):
        """
        second step in the configuration -- show form and crete entries
        """
        if info is None:
            _LOGGER.debug("configflow::configure entered....")
            return self.async_show_form(
                step_id="configure",
                data_schema=schema(),
            )
        _LOGGER.debug("configflow::configure calls to create entries")
        return self.async_create_entry(title="toutsurmoneau", data=info)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """
        create the options flow -- could be used for later configuration
        """
        return SuezOptionsFlow(config_entry)
