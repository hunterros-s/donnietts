from string import Formatter


TIME_FIELDS = frozenset({"time", "weekday", "date"})
LOCATION_FIELDS = frozenset({"location", "city", "state", "latitude", "longitude"})
WEATHER_FIELDS = frozenset(
    {
        "weather_condition",
        "current_temp",
        "high_temp",
        "low_temp",
        "wind",
        "wind_speed",
        "precip_chance",
    }
)
AVAILABLE_FIELDS = TIME_FIELDS | LOCATION_FIELDS | WEATHER_FIELDS


class InvalidTemplateError(ValueError):
    pass


def validate_template(template: str) -> str:
    normalized = template.strip()
    if not normalized:
        raise InvalidTemplateError("template must not be empty")

    try:
        parts = list(Formatter().parse(normalized))
    except ValueError as error:
        raise InvalidTemplateError(f"template syntax is invalid: {error}") from error

    for _literal, field_name, format_spec, conversion in parts:
        if field_name is None:
            continue
        if not field_name:
            raise InvalidTemplateError("automatic template fields are not supported")
        if field_name not in AVAILABLE_FIELDS:
            available = ", ".join(sorted(AVAILABLE_FIELDS))
            raise InvalidTemplateError(
                f"unknown template field {{{field_name}}}; available fields: {available}"
            )
        if conversion is not None or format_spec:
            raise InvalidTemplateError(
                f"formatting options are not supported for template field {{{field_name}}}"
            )

    return normalized
