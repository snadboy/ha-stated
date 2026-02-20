"""Runtime Variables for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ICON,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import collection
from homeassistant.helpers.collection import IDManager
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_ATTRIBUTES,
    CONF_EXPIRE_ACTION,
    CONF_EXPIRE_TO,
    CONF_PREFIX,
    CONF_TTL,
    CONF_VALUE,
    CONF_VAR_TYPE,
    DEFAULT_EXPIRE_ACTION,
    DEFAULT_TYPE,
    DOMAIN,
    EVENT_VALUE_CHANGED,
    EXPIRE_ACTION_DELETE,
    EXPIRE_ACTION_RESET,
    STORAGE_KEY,
    STORAGE_VERSION,
    TYPE_BOOLEAN,
    TYPE_NUMBER,
    TYPE_STRING,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_FIELDS = {
    vol.Required(CONF_NAME): vol.All(str, vol.Length(min=1)),
    vol.Optional(CONF_VALUE, default=""): vol.Any(str, int, float, bool, None),
    vol.Optional(CONF_VAR_TYPE, default=DEFAULT_TYPE): vol.In(
        [TYPE_BOOLEAN, TYPE_NUMBER, TYPE_STRING]
    ),
    vol.Optional(CONF_ICON): cv.icon,
    vol.Optional(CONF_ATTRIBUTES, default={}): dict,
}

SET_VALUE_SCHEMA = {
    vol.Required(CONF_VALUE): vol.Any(str, int, float, bool, None),
    vol.Optional(CONF_TTL): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional(CONF_EXPIRE_TO): vol.Any(str, int, float, bool, None),
    vol.Optional(CONF_EXPIRE_ACTION, default=DEFAULT_EXPIRE_ACTION): vol.In(
        [EXPIRE_ACTION_RESET, EXPIRE_ACTION_DELETE]
    ),
    vol.Optional(CONF_ATTRIBUTES): dict,
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Stated domain."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Runtime Variables from a config entry."""
    component = EntityComponent[Variable](_LOGGER, DOMAIN, hass)

    id_manager = IDManager()

    storage_collection = VariableStorageCollection(
        Store(hass, STORAGE_VERSION, STORAGE_KEY),
        id_manager,
    )

    collection.sync_entity_lifecycle(
        hass, DOMAIN, DOMAIN, component, storage_collection, Variable
    )

    await storage_collection.async_load()

    collection.DictStorageCollectionWebsocket(
        storage_collection, DOMAIN, DOMAIN, STORAGE_FIELDS, STORAGE_FIELDS
    ).async_setup(hass)

    _register_services(hass, storage_collection)

    component.async_register_entity_service(
        "set_value", SET_VALUE_SCHEMA, "async_set_value"
    )
    component.async_register_entity_service("toggle", None, "async_toggle")

    hass.data[DOMAIN] = {
        "component": component,
        "collection": storage_collection,
    }

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.pop(DOMAIN, None)
    return True


def _register_services(
    hass: HomeAssistant, storage_collection: VariableStorageCollection
) -> None:
    """Register stated.set, stated.delete, and stated.delete_prefix services."""

    async def async_handle_set(call: ServiceCall) -> None:
        """Handle stated.set — upsert a variable."""
        name = call.data[CONF_NAME]
        slug = slugify(name)

        create_data = {
            CONF_NAME: name,
            CONF_VALUE: call.data.get(CONF_VALUE, ""),
            CONF_VAR_TYPE: call.data.get(CONF_VAR_TYPE, DEFAULT_TYPE),
        }
        if CONF_ICON in call.data:
            create_data[CONF_ICON] = call.data[CONF_ICON]
        if CONF_ATTRIBUTES in call.data:
            create_data[CONF_ATTRIBUTES] = call.data[CONF_ATTRIBUTES]

        ttl = call.data.get(CONF_TTL)
        expire_to = call.data.get(CONF_EXPIRE_TO)
        expire_action = call.data.get(CONF_EXPIRE_ACTION, DEFAULT_EXPIRE_ACTION)

        if slug in storage_collection.data:
            await storage_collection.async_update_item(slug, create_data)
        else:
            await storage_collection.async_create_item(create_data)

        # Apply TTL after entity exists
        if ttl is not None:
            entity_id = f"{DOMAIN}.{slug}"
            comp = hass.data[DOMAIN]["component"]
            entity = comp.get_entity(entity_id)
            if entity is not None:
                entity.apply_ttl(ttl, expire_to, expire_action)

    async def async_handle_delete(call: ServiceCall) -> None:
        """Handle stated.delete — remove a variable."""
        name = call.data[CONF_NAME]
        slug = slugify(name)

        if slug not in storage_collection.data:
            _LOGGER.warning("Cannot delete '%s': variable does not exist", name)
            return

        await storage_collection.async_delete_item(slug)

    async def async_handle_delete_prefix(call: ServiceCall) -> None:
        """Handle stated.delete_prefix — remove all variables matching a prefix."""
        prefix = slugify(call.data[CONF_PREFIX])
        if not prefix:
            _LOGGER.warning("Cannot delete_prefix: empty prefix")
            return

        # Collect matching IDs first (can't mutate dict during iteration)
        to_delete = [
            item_id
            for item_id in storage_collection.data
            if item_id.startswith(prefix)
        ]

        if not to_delete:
            _LOGGER.debug("No variables match prefix '%s'", prefix)
            return

        for item_id in to_delete:
            await storage_collection.async_delete_item(item_id)

        _LOGGER.info(
            "Deleted %d variable(s) matching prefix '%s'", len(to_delete), prefix
        )

    hass.services.async_register(
        DOMAIN,
        "set",
        async_handle_set,
        schema=vol.Schema(
            {
                vol.Required(CONF_NAME): vol.All(str, vol.Length(min=1)),
                vol.Optional(CONF_VALUE, default=""): vol.Any(
                    str, int, float, bool, None
                ),
                vol.Optional(CONF_VAR_TYPE, default=DEFAULT_TYPE): vol.In(
                    [TYPE_BOOLEAN, TYPE_NUMBER, TYPE_STRING]
                ),
                vol.Optional(CONF_ICON): cv.icon,
                vol.Optional(CONF_ATTRIBUTES, default={}): dict,
                vol.Optional(CONF_TTL): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(CONF_EXPIRE_TO): vol.Any(
                    str, int, float, bool, None
                ),
                vol.Optional(
                    CONF_EXPIRE_ACTION, default=DEFAULT_EXPIRE_ACTION
                ): vol.In([EXPIRE_ACTION_RESET, EXPIRE_ACTION_DELETE]),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "delete",
        async_handle_delete,
        schema=vol.Schema(
            {
                vol.Required(CONF_NAME): vol.All(str, vol.Length(min=1)),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "delete_prefix",
        async_handle_delete_prefix,
        schema=vol.Schema(
            {
                vol.Required(CONF_PREFIX): vol.All(str, vol.Length(min=1)),
            }
        ),
    )


class VariableStorageCollection(collection.DictStorageCollection):
    """Storage collection for runtime variables."""

    CREATE_UPDATE_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_NAME): vol.All(str, vol.Length(min=1)),
            vol.Optional(CONF_VALUE, default=""): vol.Any(
                str, int, float, bool, None
            ),
            vol.Optional(CONF_VAR_TYPE, default=DEFAULT_TYPE): vol.In(
                [TYPE_BOOLEAN, TYPE_NUMBER, TYPE_STRING]
            ),
            vol.Optional(CONF_ICON): cv.icon,
            vol.Optional(CONF_ATTRIBUTES, default={}): dict,
        }
    )

    async def _process_create_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and transform creation data."""
        return self.CREATE_UPDATE_SCHEMA(data)

    @callback
    def _get_suggested_id(self, info: dict[str, Any]) -> str:
        """Suggest an ID based on the name."""
        return slugify(info[CONF_NAME])

    async def _update_data(
        self, item: dict[str, Any], update_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Return updated data."""
        return {**item, **self.CREATE_UPDATE_SCHEMA(update_data)}


class Variable(collection.CollectionEntity, RestoreEntity):
    """A runtime variable entity."""

    _attr_should_poll = False
    editable: bool = True

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize a variable."""
        self._config = config
        self._var_type: str = config.get(CONF_VAR_TYPE, DEFAULT_TYPE)
        self._value = self._coerce(config.get(CONF_VALUE, ""))
        self._attributes: dict[str, Any] = dict(config.get(CONF_ATTRIBUTES, {}))
        self._ttl_unsub: callback | None = None
        self._expires_at = None
        self._expire_to = None
        self._expire_action: str = DEFAULT_EXPIRE_ACTION

    @classmethod
    def from_storage(cls, config: dict[str, Any]) -> Variable:
        """Create from storage data."""
        return cls(config)

    @classmethod
    def from_yaml(cls, config: dict[str, Any]) -> Variable:
        """Create from YAML (unused, but required by interface)."""
        return cls(config)

    @property
    def unique_id(self) -> str | None:
        """Return unique ID."""
        return self._config.get("id")

    @property
    def name(self) -> str | None:
        """Return the name."""
        return self._config.get(CONF_NAME)

    @property
    def icon(self) -> str | None:
        """Return the icon."""
        return self._config.get(CONF_ICON)

    @property
    def state(self) -> str | None:
        """Return the state."""
        if self._var_type == TYPE_BOOLEAN:
            return STATE_ON if self._value else STATE_OFF
        if self._value is None:
            return None
        return str(self._value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {**self._attributes, "var_type": self._var_type}
        if self._expires_at is not None:
            attrs["expires_at"] = self._expires_at.isoformat()
        return attrs

    def _coerce(self, value: Any) -> Any:
        """Coerce value to the variable's type."""
        if value is None:
            return None

        if self._var_type == TYPE_BOOLEAN:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("on", "true", "1", "yes")
            return bool(value)

        if self._var_type == TYPE_NUMBER:
            if isinstance(value, (int, float)):
                return value
            try:
                if isinstance(value, str) and "." in value:
                    return float(value)
                return int(value)
            except (ValueError, TypeError):
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0

        # String type
        return str(value) if value is not None else ""

    def _get_default_expire_value(self) -> Any:
        """Return the default expiry value for the current type."""
        if self._var_type == TYPE_BOOLEAN:
            return False
        if self._var_type == TYPE_NUMBER:
            return 0
        return ""

    def _fire_value_changed(self, old_value: Any, new_value: Any) -> None:
        """Fire stated.value_changed event if value actually changed."""
        old_state = self._format_state(old_value)
        new_state = self._format_state(new_value)
        if old_state == new_state:
            return
        self.hass.bus.async_fire(
            EVENT_VALUE_CHANGED,
            {
                "entity_id": self.entity_id,
                "name": self.name,
                "var_type": self._var_type,
                "old_value": old_state,
                "new_value": new_state,
            },
        )

    def _format_state(self, value: Any) -> str | None:
        """Format a value as it would appear in entity state."""
        if self._var_type == TYPE_BOOLEAN:
            return STATE_ON if value else STATE_OFF
        if value is None:
            return None
        return str(value)

    @callback
    def apply_ttl(
        self,
        ttl: int,
        expire_to: Any = None,
        expire_action: str = DEFAULT_EXPIRE_ACTION,
    ) -> None:
        """Apply TTL to this variable."""
        # Cancel existing TTL
        if self._ttl_unsub is not None:
            self._ttl_unsub()
            self._ttl_unsub = None
            self._expires_at = None

        self._expire_action = expire_action

        if expire_to is not None:
            self._expire_to = self._coerce(expire_to)
        else:
            self._expire_to = self._get_default_expire_value()

        expire_at = dt_util.utcnow() + timedelta(seconds=ttl)
        self._expires_at = expire_at
        self._ttl_unsub = async_track_point_in_time(
            self.hass, self._ttl_expired, expire_at
        )
        self.async_write_ha_state()

    @callback
    def _cancel_ttl(self) -> None:
        """Cancel any active TTL."""
        if self._ttl_unsub is not None:
            self._ttl_unsub()
            self._ttl_unsub = None
            self._expires_at = None
            self._expire_to = None
            self._expire_action = DEFAULT_EXPIRE_ACTION

    async def _ttl_expired(self, now) -> None:
        """Handle TTL expiry."""
        self._ttl_unsub = None
        self._expires_at = None

        if self._expire_action == EXPIRE_ACTION_DELETE:
            # Delete the variable entirely
            self._expire_to = None
            self._expire_action = DEFAULT_EXPIRE_ACTION
            data = self.hass.data.get(DOMAIN)
            if data:
                sc = data["collection"]
                uid = self.unique_id
                if uid and uid in sc.data:
                    await sc.async_delete_item(uid)
            return

        # Default: reset to expire_to value
        old_value = self._value
        self._value = (
            self._expire_to
            if self._expire_to is not None
            else self._get_default_expire_value()
        )
        self._expire_to = None
        self._expire_action = DEFAULT_EXPIRE_ACTION
        self._fire_value_changed(old_value, self._value)
        self.async_write_ha_state()

    async def async_set_value(
        self,
        value: Any,
        ttl: int | None = None,
        expire_to: Any = None,
        expire_action: str = DEFAULT_EXPIRE_ACTION,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Set the value of this variable (entity service)."""
        old_value = self._value
        self._value = self._coerce(value)

        if attributes is not None:
            self._attributes.update(attributes)

        self._fire_value_changed(old_value, self._value)

        if ttl is not None:
            self.apply_ttl(ttl, expire_to, expire_action)
        else:
            self._cancel_ttl()
            self.async_write_ha_state()

    async def async_toggle(self) -> None:
        """Toggle a boolean variable."""
        if self._var_type != TYPE_BOOLEAN:
            _LOGGER.warning(
                "Cannot toggle %s: not a boolean variable (type=%s)",
                self.entity_id,
                self._var_type,
            )
            return
        old_value = self._value
        self._value = not self._value
        self._fire_value_changed(old_value, self._value)
        self.async_write_ha_state()

    async def async_update_config(self, config: dict[str, Any]) -> None:
        """Handle updated config from the collection."""
        old_value = self._value
        self._config = config
        self._var_type = config.get(CONF_VAR_TYPE, DEFAULT_TYPE)
        self._value = self._coerce(config.get(CONF_VALUE, ""))
        if CONF_ATTRIBUTES in config:
            self._attributes = dict(config[CONF_ATTRIBUTES])
        self._fire_value_changed(old_value, self._value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Entity added to HA — value already loaded from storage collection."""
        await super().async_added_to_hass()
        # Intentionally skip recorder state restoration.
        # The DictStorageCollection persists and reloads the config (including value)
        # on HA restart, so RestoreEntity restoration is not needed.
        # Restoring from the recorder would overwrite a freshly-set value from
        # stated.set (e.g., when creating a new entity with value="on", the recorder
        # might have the previous expired "off" state, causing a race condition in
        # automations that check the state immediately after calling stated.set).

    async def async_will_remove_from_hass(self) -> None:
        """Clean up TTL on removal."""
        self._cancel_ttl()
