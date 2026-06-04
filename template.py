from string import Formatter

from context import AVAILABLE_FIELDS, build_template_context


def template_fields(template):
    fields = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


def normalize_text(text):
    return " ".join(text.split())


def render_template(template, now):
    fields = template_fields(template)
    context = build_template_context(fields, now)

    try:
        return normalize_text(template.format(**context))
    except KeyError as exc:
        available = ", ".join(sorted(AVAILABLE_FIELDS))
        raise RuntimeError(f"Unknown template field {{{exc.args[0]}}}. Available fields: {available}") from exc
