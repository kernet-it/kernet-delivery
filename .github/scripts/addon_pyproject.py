# /// script
# requires-python = ">=3.10"
# dependencies = ["tomlkit==0.15.1"]
# ///
"""Check or write the whool package metadata of each addon, and the workspace members.

Each addon is a Python package that whool builds from its manifest: the version, the
Odoo dependency, the addon dependencies and the Python dependencies come from
`__manifest__.py` when the package is built. This script owns the static rest: in
each `<addon>/pyproject.toml` the tables `[build-system]`, `[project]` and
`[tool.uv.sources]` and the key `[tool.whool] odoo_series_override`, and in the root
`pyproject.toml` the list `[tool.uv.workspace] members`. It edits TOML with tomlkit,
so every other table, key and comment stays as it is.

    uv run --script .github/scripts/addon_pyproject.py          # check
    uv run --script .github/scripts/addon_pyproject.py --write  # add or update

The addon-pyproject hook runs the same check with the tomlkit of its pre-commit
environment; keep its additional_dependencies pin equal to the one above.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import InlineTable, Table

# uv needs a Python bound for the workspace, and Kernet addons follow the ruff and ty
# target of the series: 19.0 and later are checked as Python 3.12 code. whool does
# not read this field, so it is not in the metadata of the wheel for 19.0 and later.
PYTHON_BY_SERIES = {16: "3.10", 17: "3.10", 18: "3.10", 19: "3.12", 20: "3.12"}

# The fields that whool writes from the manifest when it builds the package.
DYNAMIC = (
    "version",
    "dependencies",
    "description",
    "readme",
    "license",
    "authors",
    "classifiers",
    "urls",
)

WRITE = "uv run --script .github/scripts/addon_pyproject.py --write"

# Kbot and Odoo read a short legacy version, such as `1.0` or `1.0.1`, as a version
# of the branch series, and a manifest without a version as `1.0`; the next release
# of kbot writes the full `<series>.x.y.z`. whool needs the series in the version,
# so until then `[tool.whool] odoo_series_override` gives it the branch series.
# whool also needs five parts to read the series from the version; kbot accepts a
# shorter `<series>.x.y`, such as `18.0.0.1`, which needs the override too.
LEGACY_VERSION = re.compile(r"[0-9]+\.[0-9]+(\.[0-9]+)?")
DEFAULT_VERSION = "1.0"
WHOOL_VERSION_PARTS = 5
OVERRIDE = "odoo_series_override"
ANSWERS = ".copier-answers.yml"


def find_addons(root: Path) -> list[Path]:
    return sorted(
        path.parent
        for path in root.glob("*/__manifest__.py")
        if not path.parent.name.startswith(".")
    )


def branch_series(root: Path) -> int | None:
    """Read the Odoo series of the branch from the Copier answers of the template."""
    path = root / ANSWERS
    if not path.exists():
        return None
    match = re.search(
        r"""^odoo_version:\s*["']?([0-9]+)(\.0)?["']?\s*$""",
        path.read_text("utf-8"),
        re.MULTILINE,
    )
    return int(match[1]) if match else None


def addon_series(manifest: dict, branch: int | None) -> tuple[int | None, bool]:
    """Return the Odoo series of the addon, and whether whool needs it as override."""
    version = str(manifest.get("version", DEFAULT_VERSION))
    series = version.split(".", 1)[0]
    if series.isdigit() and int(series) in PYTHON_BY_SERIES:
        return int(series), len(version.split(".")) < WHOOL_VERSION_PARTS
    if branch in PYTHON_BY_SERIES and LEGACY_VERSION.fullmatch(version):
        return branch, True
    return None, False


def managed_tables(
    addon: Path, series: int, override: bool, manifest: dict, siblings: set[str]
) -> dict[str, Any]:
    tables: dict[str, Any] = {
        "build-system": {"requires": ["whool"], "build-backend": "whool.buildapi"},
        "project": {
            "name": f"odoo-addon-{addon.name}",
            "requires-python": f">={PYTHON_BY_SERIES[series]}",
            "dynamic": list(DYNAMIC),
        },
    }
    # A sibling resolves from this checkout; for a project that takes this addon
    # from Git, uv resolves it from the same commit. Every other source belongs to
    # the root dependency groups, which nothing outside this repository reads.
    depends = sorted(set(manifest.get("depends", [])) & siblings)
    tables["sources"] = {f"odoo-addon-{name}": {"workspace": True} for name in depends}
    tables[OVERRIDE] = f"{series}.0" if override else None
    return tables


def current_tables(document: tomlkit.TOMLDocument) -> dict[str, Any]:
    data = document.unwrap()
    return {
        "build-system": data.get("build-system"),
        "project": data.get("project"),
        "sources": data.get("tool", {}).get("uv", {}).get("sources", {}),
        OVERRIDE: data.get("tool", {}).get("whool", {}).get(OVERRIDE),
    }


def sources_text(names: list[str]) -> str:
    sources = tomlkit.table()
    for name in names:
        source = tomlkit.inline_table()
        source["workspace"] = True
        sources[name] = source
    document = tomlkit.document()
    document["tool"] = {"uv": {"sources": sources}}
    return tomlkit.dumps(document)


def trailing_trivia(table: Table) -> list[Any]:
    """Take the comments and blank lines that end a table body.

    tomlkit keeps them in the table, but they come before the next header, and so
    belong to the next table.
    """
    body = table.value.body
    trailing: list[Any] = []
    while body and body[-1][0] is None:
        trailing.insert(0, body.pop()[1])
    return trailing


def set_table(container: Any, name: str, values: dict[str, Any]) -> None:
    """Set a table in place, so that the comments of the file stay where they are."""
    table = container.get(name)
    if not isinstance(table, Table):
        container[name] = values
        return
    trailing = trailing_trivia(table)
    for key in [key for key in table if key not in values]:
        del table[key]
    for key, value in values.items():
        if table.get(key) != value:
            table[key] = value
    for item in trailing:
        table.add(item)


def remove_table(document: tomlkit.TOMLDocument, *path: str) -> tomlkit.TOMLDocument:
    """Remove a table, and keep the comments that end it in the file."""
    containers: list[Any] = [document]
    for key in path[:-1]:
        containers.append(containers[-1][key])
    table = containers[-1][path[-1]]
    kept = "".join(item.as_string() for item in trailing_trivia(table))
    before = tomlkit.dumps(document)
    del containers[-1][path[-1]]
    for parent, key in zip(containers[-2::-1], path[-2::-1], strict=True):
        if not parent[key]:
            del parent[key]
    after = tomlkit.dumps(document)
    # The removed text is one span. Where blank lines let it shift, the last line
    # that fits is the one right before the next header, which the comments name.
    removed = len(before) - len(after)
    starts = [0, *(i + 1 for i, char in enumerate(after) if char == "\n")]
    fits = [
        start
        for start in starts
        if before[:start] == after[:start]
        and before[start + removed :] == after[start:]
    ]
    start = fits[-1] if fits else len(after)
    head = after[:start]
    if head.endswith("\n\n"):
        kept = kept.lstrip("\n")
    # A removed last table leaves the blank lines that came before it.
    text = (head + kept + after[start:]).rstrip("\n")
    return tomlkit.parse(f"{text}\n" if text else "")


def append_text(document: tomlkit.TOMLDocument, added: str) -> tomlkit.TOMLDocument:
    """Append tables: text after the last table cannot change the tables before it."""
    text = tomlkit.dumps(document).rstrip("\n")
    return tomlkit.parse(f"{text}\n\n{added}" if text else added)


def apply_override(
    document: tomlkit.TOMLDocument, series: str | None
) -> tomlkit.TOMLDocument:
    whool = document.get("tool", {}).get("whool")
    if series is None:
        if list(whool) != [OVERRIDE]:
            del whool[OVERRIDE]
        elif not isinstance(whool, InlineTable):
            return remove_table(document, "tool", "whool")
        elif list(document["tool"]) == ["whool"]:
            return remove_table(document, "tool")
        else:
            del document["tool"]["whool"]
        return document
    if isinstance(whool, InlineTable):
        whool[OVERRIDE] = series
        return document
    if isinstance(whool, Table):
        trailing = trailing_trivia(whool)
        whool[OVERRIDE] = series
        for item in trailing:
            whool.add(item)
        return document
    added = tomlkit.document()
    added["tool"] = {"whool": {OVERRIDE: series}}
    return append_text(document, tomlkit.dumps(added))


def has_root_keys(document: tomlkit.TOMLDocument) -> bool:
    return any(
        key is not None and (key.is_dotted() or not isinstance(item, Table))
        for key, item in document.body
    )


def apply_tables(
    document: tomlkit.TOMLDocument, wanted: dict[str, Any]
) -> tomlkit.TOMLDocument:
    if "project" not in document:
        document.pop("build-system", None)
        head = tomlkit.document()
        head["build-system"] = wanted["build-system"]
        head["project"] = wanted["project"]
        rest = tomlkit.dumps(document).strip("\n")
        if not rest:
            text = tomlkit.dumps(head)
        elif has_root_keys(document):
            # Keys before the first header are root keys, dotted or not: text in
            # front of them would put them in [project].
            text = f"{rest}\n\n{tomlkit.dumps(head)}"
        else:
            # New tables go first; the comments of the file stay where they are.
            text = f"{tomlkit.dumps(head)}\n{rest}\n"
        document = tomlkit.parse(text)
    set_table(document, "build-system", wanted["build-system"])
    set_table(document, "project", wanted["project"])
    if current_tables(document)[OVERRIDE] != wanted[OVERRIDE]:
        document = apply_override(document, wanted[OVERRIDE])
    current = document.unwrap().get("tool", {}).get("uv", {}).get("sources")
    if current == (wanted["sources"] or None):
        return document
    if current is not None:
        document = remove_table(document, "tool", "uv", "sources")
    if wanted["sources"]:
        document = append_text(document, sources_text(sorted(wanted["sources"])))
    return document


def unsupported(manifest: dict, branch: int | None) -> str:
    version = str(manifest.get("version", DEFAULT_VERSION))
    reason = f"the manifest version {version!r} names no supported Odoo series"
    if LEGACY_VERSION.fullmatch(version) and branch not in PYTHON_BY_SERIES:
        reason += f", and {ANSWERS} names no supported odoo_version"
    return reason


def check_addon(
    addon: Path, siblings: set[str], branch: int | None, *, write: bool
) -> str | None:
    manifest = ast.literal_eval((addon / "__manifest__.py").read_text("utf-8"))
    series, override = addon_series(manifest, branch)
    if series is None:
        return f"{addon.name}: {unsupported(manifest, branch)}"
    if not manifest.get("installable", True):
        return (
            f"{addon.name}: the addon is not installable, and whool cannot package it"
        )
    path = addon / "pyproject.toml"
    exists = path.exists()
    document = tomlkit.parse(path.read_text("utf-8")) if exists else tomlkit.document()
    wanted = managed_tables(addon, series, override, manifest, siblings - {addon.name})
    current = current_tables(document)
    if current == wanted:
        return None
    # The release commit of kbot writes the full version and does not run this
    # script, so the check accepts the override of the branch series that it leaves.
    leftover = {**wanted, OVERRIDE: f"{series}.0"}
    if not write and series == branch and current == leftover:
        return None
    if write:
        document = apply_tables(document, wanted)
        path.write_text(tomlkit.dumps(document), "utf-8")
        sys.stdout.write(f"{path}: written\n")
        return None
    return f"{path}: {'stale package metadata' if exists else 'missing'}"


def check_members(root: Path, addons: list[Path], *, write: bool) -> str | None:
    """Keep the workspace members equal to the addons.

    A glob such as "*" would also take a directory that is no package, such as
    dist/ after `uv build`, and uv then refuses the workspace, also for a project
    that finds it through a Git dependency.
    """
    path = root / "pyproject.toml"
    document = tomlkit.parse(path.read_text("utf-8"))
    workspace = document["tool"]["uv"]["workspace"]
    wanted = [addon.name for addon in addons]
    if workspace.get("members") == wanted:
        return None
    if write:
        members = tomlkit.array()
        members.extend(wanted)
        workspace["members"] = members.multiline(multiline=bool(wanted))
        path.write_text(tomlkit.dumps(document), "utf-8")
        sys.stdout.write(f"{path}: written\n")
        return None
    return f"{path}: stale workspace members"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--write", action="store_true", help="add or update the tables")
    parser.add_argument("root", nargs="?", type=Path, default=Path())
    args = parser.parse_args()

    addons = find_addons(args.root)
    siblings = {addon.name for addon in addons}
    branch = branch_series(args.root)
    results = [
        check_addon(addon, siblings, branch, write=args.write) for addon in addons
    ]
    results.append(check_members(args.root, addons, write=args.write))
    failures = [result for result in results if result]
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures and not args.write:
        sys.stderr.write(f"Run: {WRITE}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
