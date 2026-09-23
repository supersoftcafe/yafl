"""The -W warning-flag registry, shared by main.py and the bootstrap driver's
own equivalent (bootstrap/frontend/warnings.yafl — keep the two in sync).

Each entry's value is whether the warning is on by default. `-Wall` enables
every entry; `-Wname`/`-Wno-name` enable/disable one by name, in the order
given, starting from the default set.
"""

KNOWN_WARNINGS: dict[str, bool] = {
    "unused-parameter": False,
    "unused-variable": True,
    "discarded-value": True,
    "fragile-base": True,
}


def resolve_enabled_warnings(flags: list[str]) -> frozenset[str]:
    enabled = {name for name, default in KNOWN_WARNINGS.items() if default}
    for flag in flags:
        if flag == "all":
            enabled |= set(KNOWN_WARNINGS)
        elif flag.startswith("no-"):
            enabled.discard(_known(flag[len("no-"):]))
        else:
            enabled.add(_known(flag))
    return frozenset(enabled)


def _known(name: str) -> str:
    if name not in KNOWN_WARNINGS:
        raise ValueError(f"unknown warning '-W{name}'")
    return name
