from string import Formatter

import httpx

from context import AVAILABLE_FIELDS, build_template_context


def template_fields(template):
    fields = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


def normalize_text(text):
    return " ".join(text.split())


async def render_template(client: httpx.AsyncClient, template, now):
    fields = template_fields(template)
    context = await build_template_context(client, fields, now)

    try:
        return normalize_text(template.format(**context))
    except KeyError as exc:
        available = ", ".join(sorted(AVAILABLE_FIELDS))
        raise RuntimeError(f"Unknown template field {{{exc.args[0]}}}. Available fields: {available}") from exc
