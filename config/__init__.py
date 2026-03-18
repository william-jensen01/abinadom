"""Configuration package for LDS MCP extraction pipeline."""

from .schemas import (
    TALK_METADATA_SCHEMA,
    validate_schema,
    get_required_fields,
    get_optional_fields,
    get_default_value
)

__all__ = [
    'TALK_METADATA_SCHEMA',
    'validate_schema',
    'get_required_fields',
    'get_optional_fields',
    'get_default_value'
]
