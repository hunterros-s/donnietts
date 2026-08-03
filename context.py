"""Re-export of the package context module (legacy shim)."""

from donnietts.context import (
    CONTEXT_SETTINGS,
    ContextSettings,
    WEATHER_CODES,
    build_location_context,
    build_template_context,
    build_weather_context,
    detect_coordinates,
    get_location,
    get_weather,
)
from donnietts.template_validation import AVAILABLE_FIELDS
