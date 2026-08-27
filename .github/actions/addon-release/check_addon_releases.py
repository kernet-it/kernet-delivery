#!/usr/bin/env python3
"""Validate release metadata for addons changed between two Git revisions."""

from __future__ import annotations

import argparse
import ast
import html
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MANIFEST = "__manifest__.py"
HISTORY = PurePosixPath("readme/HISTORY.rst")
ZERO_SHA = "0" * 40
NON_RELEASE_DIRECTORIES = {"doc", "docs", "readme", "tests"}
COPIER_METADATA = {
    ".copier-answers.yaml",
    ".copier-answers.yml",
    "copier.yaml",
    "copier.yml",
}
SERIES_RE = re.compile(r"^(?P<major>[0-9]+)(?:\.0)?$")
HISTORY_HEADING_RE = re.compile(
    r"^(?P<version>[0-9]+(?:\.[0-9]+){1,4})"
    r"(?: \((?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\))?$"
)


class CheckFailure(Exception):
    """The repository or invocation cannot be checked safely."""


class VersionFailure(ValueError):
    """A manifest version is not compatible with its Odoo series."""


@dataclass(frozen=True)
class Issue:
    path: PurePosixPath | None
    message: str


@dataclass(frozen=True)
class AddonRelease:
    root: PurePosixPath
    version: str


@dataclass(frozen=True)
class GitChanges:
    paths: frozenset[PurePosixPath]
    renames: tuple[tuple[PurePosixPath, PurePosixPath], ...]


class GitRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _run(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
        )
        if check and result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise CheckFailure(f"git {' '.join(args)} failed: {detail}")
        return result

    def has_commit(self, revision: str) -> bool:
        if not revision:
            return False
        return (
            self._run(
                "cat-file", "-e", f"{revision}^{{commit}}", check=False
            ).returncode
            == 0
        )

    def files(self, revision: str) -> set[PurePosixPath]:
        payload = self._run("ls-tree", "-r", "--name-only", "-z", revision).stdout
        return {
            PurePosixPath(item.decode("utf-8", "surrogateescape"))
            for item in payload.split(b"\0")
            if item
        }

    def read(self, revision: str, path: PurePosixPath) -> str | None:
        result = self._run("show", f"{revision}:{path.as_posix()}", check=False)
        if result.returncode:
            return None
        return result.stdout.decode("utf-8", "surrogateescape")

    def changes(self, base: str, head: str) -> GitChanges:
        payload = self._run(
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            f"{base}...{head}",
        ).stdout
        tokens = [item for item in payload.split(b"\0") if item]
        paths: set[PurePosixPath] = set()
        renames: list[tuple[PurePosixPath, PurePosixPath]] = []
        index = 0
        while index < len(tokens):
            status = tokens[index].decode("ascii", "replace")
            index += 1
            if index >= len(tokens):
                raise CheckFailure("git diff returned an incomplete name-status record")
            old_path = PurePosixPath(tokens[index].decode("utf-8", "surrogateescape"))
            paths.add(old_path)
            index += 1
            if status[:1] in {"R", "C"}:
                if index >= len(tokens):
                    raise CheckFailure("git diff returned an incomplete rename record")
                new_path = PurePosixPath(
                    tokens[index].decode("utf-8", "surrogateescape")
                )
                paths.add(new_path)
                if status.startswith("R"):
                    renames.append((old_path, new_path))
                index += 1
        return GitChanges(frozenset(paths), tuple(renames))


def normalize_series(value: object) -> str:
    text = str(value).strip().strip("'\"")
    match = SERIES_RE.fullmatch(text)
    if not match:
        raise VersionFailure(f"Odoo series {text!r} must use NN or NN.0 format")
    return f"{int(match.group('major'))}.0"


def numeric_parts(version: str) -> list[int]:
    parts = version.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise VersionFailure(f"version {version!r} must contain only numeric parts")
    return [int(part) for part in parts]


def normalize_odoo_version(version: object, series: str) -> tuple[int, ...]:
    """Apply the manifest-version rules used by Odoo 16 through 19."""

    if not isinstance(version, str) or not version.strip():
        raise VersionFailure("manifest version must be a non-empty string")
    raw = version.strip()
    major = int(series.split(".", 1)[0])
    raw_parts = raw.split(".")
    expected_prefix = tuple(int(part) for part in series.split("."))
    if (
        len(raw_parts) in {4, 5}
        and all(part.isdigit() for part in raw_parts)
        and int(raw_parts[0]) >= 16
        and int(raw_parts[1]) == 0
        and tuple(int(part) for part in raw_parts[:2]) != expected_prefix
    ):
        raise VersionFailure(
            f"version {raw!r} explicitly disagrees with Odoo series {series}"
        )

    if major <= 16:
        adapted = raw
        if raw == series or not raw.startswith(series + "."):
            adapted = f"{series}.{raw}"
    elif major in {17, 18}:
        if raw == series or not raw.startswith(series + "."):
            base_version = raw
            adapted = f"{series}.{raw}"
        else:
            base_version = raw[len(series) + 1 :]
            adapted = raw
        base_parts = base_version.split(".")
        if len(base_parts) not in {2, 3} or any(
            not part.isdigit() for part in base_parts
        ):
            raise VersionFailure(
                f"version {raw!r} is not accepted by Odoo {series}; use x.y, "
                f"x.y.z, {series}.x.y, or {series}.x.y.z"
            )
    else:
        raw_parts = numeric_parts(raw)
        if not 2 <= len(raw_parts) <= 5:
            raise VersionFailure(
                f"version {raw!r} is not accepted by Odoo {series}; "
                "it must have between two and five parts"
            )
        adapted = raw
        if len(raw_parts) <= 3 and not raw.startswith(series):
            adapted = f"{series}.{raw}"
        if not adapted.startswith(series + "."):
            raise VersionFailure(
                f"version {raw!r} explicitly disagrees with Odoo series {series}"
            )

    parts = numeric_parts(adapted)
    if tuple(parts[:2]) != expected_prefix:
        raise VersionFailure(
            f"version {raw!r} explicitly disagrees with Odoo series {series}"
        )
    if major > 16 and len(parts) > 5:
        raise VersionFailure(f"version {raw!r} has too many parts to compare safely")
    parts.extend([0] * (5 - len(parts)))
    return tuple(parts)


def version_key(parts: tuple[int, ...]) -> tuple[int, ...]:
    trimmed = list(parts)
    while trimmed and trimmed[-1] == 0:
        trimmed.pop()
    return tuple(trimmed)


def canonical_version(version: object, series: str) -> tuple[int, int, int, int, int]:
    if not isinstance(version, str):
        raise VersionFailure("the new manifest version must be a string")
    raw = version.strip()
    parts = numeric_parts(raw)
    if len(parts) != 5:
        raise VersionFailure(
            f"the new version {version!r} must use canonical {series}.x.y.z format"
        )
    if version != raw or raw != ".".join(str(part) for part in parts):
        raise VersionFailure(
            f"the new version {version!r} must use canonical {series}.x.y.z format"
        )
    expected_prefix = tuple(int(part) for part in series.split("."))
    if tuple(parts[:2]) != expected_prefix:
        raise VersionFailure(
            f"the new version {version!r} explicitly disagrees with Odoo series {series}"
        )
    return parts[0], parts[1], parts[2], parts[3], parts[4]


def addon_roots(
    files: set[PurePosixPath], layout: str
) -> dict[PurePosixPath, PurePosixPath]:
    roots: dict[PurePosixPath, PurePosixPath] = {}
    for path in files:
        parts = path.parts
        if not parts or parts[-1] != MANIFEST:
            continue
        if layout == "addon-group" and len(parts) == 2:
            root = PurePosixPath(parts[0])
        elif (
            layout == "project"
            and len(parts) == 3
            and parts[0] in {"addons", "extra-addons"}
        ):
            root = PurePosixPath(parts[0], parts[1])
        else:
            continue
        roots[root] = path
    return roots


def path_in_addon(path: PurePosixPath, root: PurePosixPath) -> PurePosixPath | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def containing_addon(
    path: PurePosixPath, roots: dict[PurePosixPath, PurePosixPath]
) -> PurePosixPath | None:
    return next((root for root in roots if path_in_addon(path, root) is not None), None)


def release_relevant(path: PurePosixPath) -> bool:
    if not path.parts:
        return False
    lower_parts = tuple(part.lower() for part in path.parts)
    first_lower = lower_parts[0]
    if first_lower in NON_RELEASE_DIRECTORIES:
        return False
    if "tests" in lower_parts:
        return False
    if (
        first_lower == "static"
        and len(path.parts) > 1
        and path.parts[1].lower() == "description"
    ):
        return False
    if first_lower in COPIER_METADATA:
        return False
    return not first_lower.startswith("readme")


def parse_manifest(
    content: str | None,
    path: PurePosixPath,
    *,
    default_version: str | None = None,
) -> dict[str, object]:
    if content is None:
        raise CheckFailure(f"cannot read {path}")
    try:
        manifest = ast.literal_eval(content)
    except (SyntaxError, ValueError) as error:
        raise CheckFailure(
            f"{path} is not a literal Python manifest: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise CheckFailure(f"{path} must contain a dictionary")
    if "version" not in manifest:
        if default_version is None:
            raise CheckFailure(f"{path} has no version")
        manifest = {**manifest, "version": default_version}
    return manifest


def env_odoo_series(content: str | None) -> str | None:
    if content is None:
        return None
    selected: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key == "ODOO_VERSION":
            selected = value.split("#", 1)[0].strip()
    return normalize_series(selected) if selected is not None else None


def toml_odoo_series(content: str | None) -> str | None:
    if content is None:
        return None
    try:
        project = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise CheckFailure(f"cannot parse pyproject.toml: {error}") from error
    value = project.get("tool", {}).get("kernet", {}).get("odoo_version")
    return normalize_series(value) if value is not None else None


def project_series(repository: GitRepository, revision: str) -> str | None:
    from_toml = toml_odoo_series(
        repository.read(revision, PurePosixPath("pyproject.toml"))
    )
    from_env = env_odoo_series(repository.read(revision, PurePosixPath(".env")))
    if from_toml and from_env and from_toml != from_env:
        raise CheckFailure(
            f"pyproject.toml selects Odoo {from_toml}, but .env selects Odoo {from_env}"
        )
    return from_toml or from_env


def history_version(content: str | None) -> tuple[str, bool] | None:
    if content is None:
        return None
    lines = content.splitlines()
    heading = next(
        (
            (index, match)
            for index, line in enumerate(lines)
            if (match := HISTORY_HEADING_RE.fullmatch(line.strip())) is not None
        ),
        None,
    )
    if heading is None:
        return None
    heading_index, match = heading
    remainder = lines[heading_index + 1 :]
    if remainder:
        adornment = remainder[0].strip()
        if adornment and len(set(adornment)) == 1 and not adornment[0].isalnum():
            remainder = remainder[1:]
    next_heading = next(
        (
            index
            for index, line in enumerate(remainder)
            if HISTORY_HEADING_RE.fullmatch(line.strip())
        ),
        None,
    )
    if next_heading is not None:
        remainder = remainder[:next_heading]
    has_content = any(line.strip() for line in remainder)
    return match.group("version"), has_content


def annotation_escape(value: str, *, property_value: bool = False) -> str:
    escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        escaped = escaped.replace(":", "%3A").replace(",", "%2C")
    return escaped


def emit_issue(issue: Issue) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        properties = "title=Addon release metadata"
        if issue.path is not None:
            properties = (
                f"file={annotation_escape(issue.path.as_posix(), property_value=True)},"
                + properties
            )
        print(f"::error {properties}::{annotation_escape(issue.message)}")
    else:
        location = f"{issue.path}: " if issue.path is not None else ""
        print(f"ERROR: {location}{issue.message}", file=sys.stderr)


def summary_escape(value: str) -> str:
    flattened = " ".join(value.splitlines())
    return html.escape(flattened, quote=False).replace("`", "&#96;")


def write_summary(checked: list[AddonRelease], issues: list[Issue]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = ["### Addon releases", ""]
    if issues:
        lines.append(f"Failed with {len(issues)} release metadata error(s).")
        lines.append("")
        lines.extend(f"- {summary_escape(issue.message)}" for issue in issues)
    elif checked:
        lines.extend(
            f"- `{summary_escape(release.root.as_posix())}`: "
            f"`{summary_escape(release.version)}`"
            for release in checked
        )
    else:
        lines.append("No release-relevant addon changes.")
    with open(summary_path, "a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def check_releases(
    repository: GitRepository,
    *,
    base: str,
    head: str,
    layout: str,
    configured_series: str | None,
) -> tuple[list[AddonRelease], list[Issue]]:
    base_files = repository.files(base)
    head_files = repository.files(head)
    base_roots = addon_roots(base_files, layout)
    head_roots = addon_roots(head_files, layout)
    all_roots = set(base_roots) | set(head_roots)
    changes = repository.changes(base, head)
    changed_paths = changes.paths
    renamed_candidates: dict[PurePosixPath, set[PurePosixPath]] = {}
    for old_path, new_path in changes.renames:
        old_root = containing_addon(old_path, base_roots)
        new_root = containing_addon(new_path, head_roots)
        if (
            old_root is not None
            and new_root is not None
            and old_root not in head_roots
            and new_root not in base_roots
        ):
            renamed_candidates.setdefault(new_root, set()).add(old_root)
    renamed_base_roots = {
        new_root: next(iter(old_roots))
        for new_root, old_roots in renamed_candidates.items()
        if len(old_roots) == 1
    }

    impacted: dict[PurePosixPath, set[PurePosixPath]] = {}
    for path in changed_paths:
        for root in all_roots:
            relative = path_in_addon(path, root)
            if relative is not None and release_relevant(relative):
                impacted.setdefault(root, set()).add(path)

    if not impacted:
        return [], []

    if layout == "addon-group":
        if not configured_series:
            raise CheckFailure("addon-group checks require an Odoo series")
        head_series = base_series = normalize_series(configured_series)
    else:
        head_series = project_series(repository, head)
        base_series = project_series(repository, base)
        if head_series is None:
            raise CheckFailure(
                "cannot find the project Odoo series in pyproject.toml "
                "[tool.kernet].odoo_version or .env ODOO_VERSION"
            )
        base_series = base_series or head_series

    checked: list[AddonRelease] = []
    issues: list[Issue] = []
    for root in sorted(impacted, key=lambda item: item.as_posix()):
        manifest_path = root / MANIFEST
        if root not in head_roots:
            remaining = any(
                path_in_addon(path, root) is not None for path in head_files
            )
            if remaining:
                issues.append(
                    Issue(
                        manifest_path,
                        f"{root}: manifest was removed but addon files remain",
                    )
                )
            continue

        try:
            head_manifest = parse_manifest(
                repository.read(head, manifest_path), manifest_path
            )
        except CheckFailure as error:
            issues.append(Issue(manifest_path, f"{root}: {error}"))
            continue

        head_version = head_manifest["version"]
        try:
            normalized_head = canonical_version(head_version, head_series)
        except VersionFailure as error:
            issues.append(Issue(manifest_path, f"{root}: {error}"))
            normalized_head = None

        base_root = root if root in base_roots else renamed_base_roots.get(root)
        if base_root is not None and normalized_head is not None:
            base_manifest_path = base_roots[base_root]
            try:
                base_manifest = parse_manifest(
                    repository.read(base, base_manifest_path),
                    base_manifest_path,
                    default_version="1.0",
                )
                normalized_base = normalize_odoo_version(
                    base_manifest["version"], base_series
                )
            except (CheckFailure, VersionFailure):
                # The head can adopt canonical metadata even when immutable
                # legacy metadata cannot be compared safely.
                pass
            else:
                if version_key(normalized_head) <= version_key(normalized_base):
                    old_version = base_manifest["version"]
                    issues.append(
                        Issue(
                            manifest_path,
                            f"{root}: version did not increase from the base branch: "
                            f"{old_version} -> {head_version}; rebase if the base advanced",
                        )
                    )

        history_path = root / HISTORY
        if history_path not in changed_paths:
            issues.append(
                Issue(
                    history_path,
                    f"{root}: {HISTORY} must change with the addon release",
                )
            )
        parsed_history = history_version(repository.read(head, history_path))
        if parsed_history is None:
            issues.append(
                Issue(
                    history_path,
                    f"{root}: {HISTORY} must start with the new version",
                )
            )
        else:
            top_version, has_content = parsed_history
            if top_version != head_version:
                issues.append(
                    Issue(
                        history_path,
                        f"{root}: changelog version {top_version} does not match "
                        f"manifest version {head_version}",
                    )
                )
            if not has_content:
                issues.append(
                    Issue(history_path, f"{root}: the new changelog entry is empty")
                )

        if normalized_head is not None and isinstance(head_version, str):
            checked.append(AddonRelease(root, head_version))

    return checked, issues


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--layout", choices=("addon-group", "project"), required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--series", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repository = GitRepository(args.repository)
    if not repository.has_commit(args.head):
        print(f"ERROR: head revision {args.head!r} is not available", file=sys.stderr)
        return 2
    if not args.base or args.base == ZERO_SHA:
        print("No usable base revision; addon release check skipped.")
        write_summary([], [])
        return 0
    if not repository.has_commit(args.base):
        print(
            f"ERROR: base revision {args.base!r} is not available; use a full-history checkout",
            file=sys.stderr,
        )
        return 2
    try:
        checked, issues = check_releases(
            repository,
            base=args.base,
            head=args.head,
            layout=args.layout,
            configured_series=args.series or None,
        )
    except (CheckFailure, VersionFailure) as error:
        issue = Issue(None, str(error))
        emit_issue(issue)
        write_summary([], [issue])
        return 2

    for issue in issues:
        emit_issue(issue)
    write_summary(checked, issues)
    if issues:
        print(
            f"Addon release check failed with {len(issues)} error(s).", file=sys.stderr
        )
        return 1
    if checked:
        rendered = ", ".join(f"{item.root}={item.version}" for item in checked)
        print(f"Addon releases valid: {rendered}")
    else:
        print("No release-relevant addon changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
