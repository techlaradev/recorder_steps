


import re


def slugify(value: str) -> str:
    value = value.strip().lower()

    value = re.sub(
        r"[^\w\s-]",
        "",
        value,
    )

    value = re.sub(
        r"[\s_]+",
        "-",
        value,
    )

    value = re.sub(
        r"-+",
        "-",
        value,
    )

    return value.strip("-")