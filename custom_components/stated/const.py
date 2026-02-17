"""Constants for the Stated integration."""

DOMAIN = "stated"
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

CONF_VALUE = "value"
CONF_VAR_TYPE = "var_type"
CONF_ATTRIBUTES = "attributes"
CONF_TTL = "ttl"
CONF_EXPIRE_TO = "expire_to"
CONF_EXPIRE_ACTION = "expire_action"
CONF_PREFIX = "prefix"

TYPE_BOOLEAN = "boolean"
TYPE_NUMBER = "number"
TYPE_STRING = "string"
DEFAULT_TYPE = TYPE_STRING

EXPIRE_ACTION_RESET = "reset"
EXPIRE_ACTION_DELETE = "delete"
DEFAULT_EXPIRE_ACTION = EXPIRE_ACTION_RESET

EVENT_VALUE_CHANGED = f"{DOMAIN}.value_changed"
