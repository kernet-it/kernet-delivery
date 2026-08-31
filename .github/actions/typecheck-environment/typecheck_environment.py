from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

DIST_NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
PRIVATE_VCS = re.compile(
    rf"^(?P<name>{DIST_NAME})(?P<extras>\[[^]]+\])?\s*@\s*"
    r"git\+https://github\.com/kernet-it/"
    rf"(?P<repository>{DIST_NAME})\.git"
    r"(?:@(?P<ref>[^;\s]+))?"
    r"(?:\s*;\s*(?P<marker>.+))?$"
)
TY_HOOK = re.compile(r"^\s*-\s+id\s*:\s*['\"]?ty['\"]?\s*(?:#.*)?$", re.MULTILINE)
SUPPORTED_PYTHON_VERSIONS = {"3.10", "3.12"}
SUPPORTED_TYPECHECK_POLICIES = {"incremental", "strict"}
FETCHED_PROJECT_ROOTS = {"kernet", "oca"}
OWNED_ADDON_ROOTS = {"addons", "extra-addons"}


def canonical(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def validate_odoo_version(value: str) -> str:
    match = re.fullmatch(r"(?P<major>[0-9]+)(?:\.0)?", value.strip())
    if match is None:
        raise ValueError("Odoo version must use NN or NN.0 format")
    return f"{match.group('major')}.0"


def validate_typecheck_policy(value: str) -> str:
    value = value.strip() or "strict"
    if value not in SUPPORTED_TYPECHECK_POLICIES:
        choices = ", ".join(sorted(SUPPORTED_TYPECHECK_POLICIES))
        raise ValueError(f"type-check policy must be one of: {choices}")
    return value


def write_lines(path: Path, entries: Iterable[str]) -> None:
    lines = list(dict.fromkeys(entries))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        for name, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"multiline GitHub output for {name!r}")
            stream.write(f"{name}={value}\n")


def git_commit_exists(revision: str) -> bool:
    if not revision:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", f"{revision}^{{commit}}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def changed_entries(
    base: str, head: str
) -> tuple[list[tuple[str, Path, Path | None]], bool]:
    usable_base = git_commit_exists(base) and git_commit_exists(head or "HEAD")
    if usable_base:
        resolved_head = head or "HEAD"
        has_merge_base = (
            subprocess.run(
                ["git", "merge-base", base, resolved_head],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        revisions = (
            [f"{base}...{resolved_head}"] if has_merge_base else [base, resolved_head]
        )
        command = [
            "git",
            "diff",
            "--name-status",
            "--find-renames",
            "-z",
            *revisions,
        ]
        values = subprocess.run(
            command, check=True, stdout=subprocess.PIPE
        ).stdout.split(b"\0")
        entries: list[tuple[str, Path, Path | None]] = []
        index = 0
        while index < len(values) and values[index]:
            status = values[index].decode()
            index += 1
            source = Path(values[index].decode())
            index += 1
            target = None
            if status.startswith(("R", "C")):
                target = Path(values[index].decode())
                index += 1
            entries.append((status, source, target))
        return entries, True
    else:
        output = subprocess.run(
            ["git", "ls-files", "-z"], check=True, stdout=subprocess.PIPE
        ).stdout
        return [
            ("A", Path(value.decode()), None) for value in output.split(b"\0") if value
        ], False


def is_python_source(path: Path) -> bool:
    if path.suffix in {".py", ".pyi"}:
        return True
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(256)
    except (FileNotFoundError, IsADirectoryError, OSError):
        return False
    return first_line.startswith(b"#!") and b"python" in first_line.lower()


def is_typecheck_configuration(path: Path, layout: str) -> bool:
    if path in {Path(".env"), Path(".pre-commit-config.yaml"), Path("ty.toml")}:
        return True
    if path == Path("pyproject.toml"):
        return True
    if (
        layout in {"auto", "project"}
        and len(path.parts) > 1
        and path.parts[0] == "dependencies"
    ):
        return True
    if path.name != "pyproject.toml":
        return False
    if (
        layout in {"auto", "project"}
        and len(path.parts) == 3
        and path.parts[0] in OWNED_ADDON_ROOTS
    ):
        return True
    return (
        layout in {"auto", "addon-group"}
        and len(path.parts) == 2
        and path.parts[0] not in FETCHED_PROJECT_ROOTS
    )


def typecheck_required(
    *,
    enabled: bool,
    precommit_config: str,
    entries: Iterable[tuple[str, Path, Path | None]],
    usable_base: bool,
    layout: str = "auto",
    policy: str = "strict",
) -> tuple[bool, str, str]:
    policy = validate_typecheck_policy(policy)
    if not enabled:
        return False, "disabled", "none"
    if not TY_HOOK.search(precommit_config):
        return False, "no-ty-hook", "none"
    saw_python = False
    saw_configuration = False
    saw_deleted_python = False
    saw_renamed_python = False
    for status, source, target in entries:
        paths = (source,) if target is None else (source, target)
        saw_configuration = saw_configuration or any(
            is_typecheck_configuration(path, layout) for path in paths
        )
        saw_deleted_python = saw_deleted_python or (
            status.startswith("D")
            and any(path.suffix in {".py", ".pyi"} for path in paths)
        )
        saw_renamed_python = saw_renamed_python or (
            status.startswith("R") and source.suffix in {".py", ".pyi"}
        )
        candidate = target or source
        saw_python = saw_python or is_python_source(candidate)
    if saw_deleted_python:
        return True, "python-deleted", "all"
    if saw_renamed_python:
        return True, "python-renamed", "all"
    if saw_configuration:
        if policy == "strict" or not usable_base:
            return True, "configuration-changed", "all"
        if saw_python:
            return True, "configuration-changed", "changed"
        return False, "incremental-configuration-only", "none"
    if saw_python:
        mode = "changed" if usable_base else "all"
        return True, "python-changed", mode
    return False, "no-python-changes", "none"


def private_vcs_requirement(entry: str) -> dict[str, str] | None:
    if "kernet-it/" not in entry or "git+" not in entry:
        return None
    match = PRIVATE_VCS.fullmatch(entry.strip())
    if match is None:
        raise ValueError(
            "private Kernet dependencies must use "
            "'name @ git+https://github.com/kernet-it/repository.git[@ref]'"
        )
    ref = match.group("ref") or ""
    if ref and not re.fullmatch(r"[0-9a-f]{40}", ref):
        valid_ref = subprocess.run(
            ["git", "check-ref-format", "--branch", ref],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if valid_ref.returncode:
            raise ValueError(f"invalid private dependency ref: {ref!r}")
    return match.groupdict(default="")


def logical_requirement_lines(content: str) -> list[str]:
    entries: list[str] = []
    pending = ""
    for raw_line in content.splitlines():
        line = re.split(r"\s+#", raw_line.strip(), maxsplit=1)[0].rstrip()
        if not line or line.startswith("#"):
            continue
        if pending:
            line = pending + line
            pending = ""
        if line.endswith("\\"):
            pending = line[:-1].rstrip() + " "
            continue
        entries.append(line)
    if pending:
        raise ValueError("unterminated requirement line continuation")
    return entries


def requirement_include(entry: str) -> tuple[str, str] | None:
    if not entry.startswith(("-r", "--requirement", "-c", "--constraint")):
        return None
    tokens = shlex.split(entry, comments=True)
    if not tokens:
        return None
    option = tokens[0]
    if option in {"-r", "--requirement", "-c", "--constraint"}:
        if len(tokens) != 2:
            raise ValueError(f"invalid requirement-file include: {entry!r}")
        kind = "requirement" if option in {"-r", "--requirement"} else "constraint"
        return kind, tokens[1]
    for prefix, kind in (
        ("--requirement=", "requirement"),
        ("--constraint=", "constraint"),
        ("-r", "requirement"),
        ("-c", "constraint"),
    ):
        if option.startswith(prefix) and len(option) > len(prefix) and len(tokens) == 1:
            return kind, option[len(prefix) :]
    return None


def legacy_requirements(path: Path, root: Path) -> list[str]:
    repository_root = root.resolve()
    dependency_root = path.parent.resolve()
    visited: set[tuple[Path, str]] = set()
    stack: set[Path] = set()
    requirements: list[str] = []

    def visit(current: Path, kind: str) -> None:
        resolved = current.resolve()
        if not resolved.is_relative_to(repository_root):
            raise ValueError(f"requirement include leaves the repository: {current}")
        if not resolved.is_relative_to(dependency_root):
            raise ValueError(
                f"requirement include leaves the dependencies directory: {current}"
            )
        if resolved in stack:
            raise ValueError(f"cyclic requirement-file include: {resolved}")
        key = (resolved, kind)
        if key in visited:
            return
        if not resolved.is_file():
            raise ValueError(f"requirement include does not exist: {resolved}")
        stack.add(resolved)
        for entry in logical_requirement_lines(resolved.read_text(encoding="utf-8")):
            include = requirement_include(entry)
            if include is None:
                if kind == "requirement" and not entry.startswith("-"):
                    requirements.append(entry)
                continue
            include_kind, include_path = include
            if "://" in include_path:
                raise ValueError(
                    "remote requirement or constraint file include is not "
                    f"supported: {include_path}"
                )
            visit(resolved.parent / include_path, include_kind)
        stack.remove(resolved)
        visited.add(key)

    visit(path, "requirement")
    return requirements


def dependency_table(path: Path) -> tuple[list[str], list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    dependencies = data.get("tool", {}).get("kernet", {}).get("dependencies", {})
    requirements = dependencies.get("python", [])
    constraints = dependencies.get("constraints", [])
    if not isinstance(requirements, list) or not all(
        isinstance(entry, str) for entry in requirements
    ):
        raise ValueError(f"{path}: [tool.kernet.dependencies].python must be a list")
    if not isinstance(constraints, list) or not all(
        isinstance(entry, str) for entry in constraints
    ):
        raise ValueError(
            f"{path}: [tool.kernet.dependencies].constraints must be a list"
        )
    return requirements, constraints


def has_project_metadata(path: Path) -> bool:
    if not path.is_file():
        return False
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    kernet = data.get("tool", {}).get("kernet")
    if not isinstance(kernet, dict):
        return kernet is not None
    return "dependencies" in kernet or "odoo_version" in kernet


def dependency_files(root: Path, layout: str) -> tuple[str, list[Path], Path | None]:
    root_project = root / "pyproject.toml"
    addon_group_projects = sorted(
        path
        for path in root.glob("*/pyproject.toml")
        if path.parent.name not in FETCHED_PROJECT_ROOTS
    )
    if layout == "auto":
        if (root / "dependencies/pip.txt").is_file() or has_project_metadata(
            root_project
        ):
            layout = "project"
        elif addon_group_projects:
            layout = "addon-group"
        else:
            layout = "project" if root_project.is_file() else "addon-group"
    if layout == "addon-group":
        pyprojects = addon_group_projects
        legacy = None
    elif layout == "project":
        pyprojects = []
        if root_project.is_file():
            pyprojects.append(root_project)
        for addon_root in ("addons", "extra-addons"):
            pyprojects.extend(sorted((root / addon_root).glob("*/pyproject.toml")))
        legacy_path = root / "dependencies/pip.txt"
        legacy = legacy_path if legacy_path.is_file() else None
    else:
        raise ValueError(f"unsupported repository layout: {layout!r}")
    return layout, pyprojects, legacy


def env_odoo_version(path: Path) -> str | None:
    if not path.is_file():
        return None
    value = None
    assignment = re.compile(r"^\s*(?:export\s+)?ODOO_VERSION\s*=\s*(?P<value>[^\s#]+)")
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := assignment.match(line):
            value = match.group("value").strip("'\"")
    return value


def project_odoo_version(path: Path) -> str | None:
    if not path.is_file():
        return None
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    value = data.get("tool", {}).get("kernet", {}).get("odoo_version")
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{path}: [tool.kernet].odoo_version must be a string")
    return value


def resolve_odoo_version(root: Path, explicit: str) -> str:
    candidates = {
        name: validate_odoo_version(value)
        for name, value in (
            ("input", explicit),
            ("pyproject.toml", project_odoo_version(root / "pyproject.toml") or ""),
            (".env", env_odoo_version(root / ".env") or ""),
        )
        if value
    }
    if not candidates:
        raise ValueError(
            "Odoo version is not configured; set odoo-version, "
            "[tool.kernet].odoo_version, or .env ODOO_VERSION"
        )
    versions = set(candidates.values())
    if len(versions) != 1:
        details = ", ".join(f"{name}={value}" for name, value in candidates.items())
        raise ValueError(f"conflicting Odoo versions: {details}")
    return next(iter(versions))


def ty_environment(root: Path) -> tuple[str, bool]:
    python_version = "3.10"
    needs_odoo = True
    ty_path = root / "ty.toml"
    if ty_path.is_file():
        config = tomllib.loads(ty_path.read_text(encoding="utf-8"))
        python_version = config.get("environment", {}).get(
            "python-version", python_version
        )
        excused = config.get("analysis", {}).get("allowed-unresolved-imports", [])
        needs_odoo = not any(
            pattern in {"odoo", "odoo.*", "odoo.**"} for pattern in excused
        )
    if python_version not in SUPPORTED_PYTHON_VERSIONS:
        raise ValueError(f"unsupported Python version selector: {python_version}")
    return python_version, needs_odoo


def collect_metadata(
    root: Path, state: Path, layout: str, explicit_odoo_version: str = ""
) -> dict[str, str]:
    resolved_layout, pyprojects, legacy = dependency_files(root, layout)
    requirements: list[str] = []
    constraints: list[str] = []
    install_entries: list[str] = []
    if legacy is not None:
        requirements.extend(legacy_requirements(legacy, root))
        install_entries.append(f"-r {legacy.resolve()}")
    for pyproject in pyprojects:
        project_requirements, project_constraints = dependency_table(pyproject)
        requirements.extend(project_requirements)
        install_entries.extend(project_requirements)
        constraints.extend(project_constraints)
    install_entries = list(dict.fromkeys(install_entries))
    requirements = sorted(set(requirements))
    constraints = sorted(set(constraints))
    private = [private_vcs_requirement(entry) for entry in requirements]
    private = [entry for entry in private if entry is not None]
    python_version, needs_odoo = ty_environment(root)
    odoo_version = resolve_odoo_version(root, explicit_odoo_version)
    state.mkdir(parents=True, exist_ok=True)
    write_lines(state / "requirements.txt", install_entries)
    write_lines(state / "constraints.txt", constraints)
    (state / "declared-requirements.json").write_text(
        json.dumps(requirements, sort_keys=True), encoding="utf-8"
    )
    (state / "private-requirements.json").write_text(
        json.dumps(private, sort_keys=True), encoding="utf-8"
    )
    (state / "needs-odoo-source").write_text(
        "1" if needs_odoo else "", encoding="utf-8"
    )
    return {
        "layout": resolved_layout,
        "odoo-version": odoo_version,
        "python-version": python_version,
    }


def requirements_at(directory: Path, commit: str) -> list[str]:
    result = subprocess.run(
        ["/usr/bin/git", "-C", directory, "show", f"{commit}:pyproject.toml"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        return []
    data = tomllib.loads(result.stdout.decode())
    project = data.get("project", {})
    entries = list(project.get("dependencies", []))
    for optional in project.get("optional-dependencies", {}).values():
        entries.extend(optional)
    entries.extend(data.get("build-system", {}).get("requires", []))
    entries.extend(
        data.get("tool", {}).get("kernet", {}).get("dependencies", {}).get("python", [])
    )
    return entries


def private_git_environment(token: str) -> tuple[dict[str, str], str]:
    authorization = (
        "AUTHORIZATION: basic "
        + base64.b64encode(f"x-access-token:{token}".encode()).decode()
    )
    environment = {
        key: value for key, value in os.environ.items() if key != "DEPENDENCY_TOKEN"
    }
    environment.update(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": authorization,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment, authorization


def assert_git_metadata_has_no_credentials(
    directory: Path, credentials: Iterable[str]
) -> None:
    encoded = [credential.encode() for credential in credentials]
    for path in (directory / ".git").rglob("*"):
        relative = path.relative_to(directory / ".git")
        if not path.is_file() or path.is_symlink() or relative.parts[0] == "objects":
            continue
        content = path.read_bytes()
        if any(credential in content for credential in encoded):
            raise ValueError("Git persisted private dependency credentials")


def fetch_private_dependencies(
    state: Path,
    token: str,
    repository_base_url: str = "https://github.com/kernet-it",
) -> None:
    root = state / "private-sources"
    root.mkdir()
    git_environment, authorization = private_git_environment(token)
    queue = json.loads((state / "private-requirements.json").read_text())
    sources: dict[str, dict[str, object]] = {}
    distributions: dict[str, str] = {}
    while queue:
        requirement = queue.pop(0)
        repository = requirement["repository"]
        repository_key = repository.lower()
        ref = requirement["ref"]
        name = canonical(requirement["name"])
        if name in distributions and distributions[name] != repository_key:
            raise ValueError(
                f"private distribution {name!r} uses multiple repositories"
            )
        distributions[name] = repository_key
        if repository_key in sources:
            if sources[repository_key]["ref"] != ref:
                raise ValueError(
                    f"private repository {repository!r} uses multiple refs"
                )
            names = sources[repository_key]["names"]
            assert isinstance(names, set)
            names.add(name)
            continue
        directory = root / repository
        directory.mkdir()
        subprocess.run(["/usr/bin/git", "-C", directory, "init", "-q"], check=True)
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                directory,
                "remote",
                "add",
                "origin",
                f"{repository_base_url.rstrip('/')}/{repository}.git",
            ],
            check=True,
        )
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                directory,
                "fetch",
                "-q",
                "--depth=1",
                "origin",
                ref or "HEAD",
            ],
            check=True,
            env=git_environment,
        )
        commit = subprocess.check_output(
            [
                "/usr/bin/git",
                "-C",
                directory,
                "rev-parse",
                "FETCH_HEAD^{commit}",
            ],
            text=True,
        ).strip()
        if re.fullmatch(r"[0-9a-f]{40}", ref) and commit != ref:
            raise ValueError(
                f"private repository {repository!r} resolved the wrong commit"
            )
        (directory / ".git/FETCH_HEAD").unlink()
        assert_git_metadata_has_no_credentials(directory, (token, authorization))
        sources[repository_key] = {
            "commit": commit,
            "names": {name},
            "path": str(directory),
            "ref": ref,
            "repository": repository,
        }
        for entry in requirements_at(directory, commit):
            nested = private_vcs_requirement(entry)
            if nested is not None and marker_active(nested["marker"]):
                queue.append(nested)
    serialized = [
        {**source, "names": sorted(source["names"])} for source in sources.values()
    ]
    (state / "private-sources.json").write_text(
        json.dumps(serialized, sort_keys=True), encoding="utf-8"
    )


def materialize_private_dependencies(state: Path) -> None:
    sources = json.loads((state / "private-sources.json").read_text())
    overrides: list[str] = []
    for source in sources:
        directory = source["path"]
        commit = source["commit"]
        subprocess.run(
            ["/usr/bin/git", "-C", directory, "cat-file", "-e", f"{commit}^{{commit}}"],
            check=True,
        )
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                directory,
                "checkout",
                "-q",
                "--detach",
                commit,
            ],
            check=True,
        )
        for name in source["names"]:
            overrides.append(f"{name} @ file://{directory}")
            print(
                f"::notice title=typecheck environment::{name} uses "
                f"{source['repository']}@{commit}"
            )
    write_lines(state / "private-overrides.txt", sorted(overrides))


def distribution_name(entry: str) -> str | None:
    from packaging.markers import Marker
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name

    egg = re.compile(rf"[#&]egg=(?P<name>{DIST_NAME})")
    try:
        parsed = Requirement(entry)
    except InvalidRequirement:
        requirement, _, marker = entry.partition(";")
        match = egg.search(requirement)
        if not match or (marker.strip() and not Marker(marker).evaluate()):
            return None
        return str(canonicalize_name(match.group("name")))
    if parsed.marker is not None and not parsed.marker.evaluate():
        return None
    return str(canonicalize_name(parsed.name))


def write_declared_names(state: Path) -> None:
    requirements = json.loads((state / "declared-requirements.json").read_text())
    names = sorted(
        {
            name
            for entry in requirements
            if (name := distribution_name(entry)) is not None
        }
    )
    write_lines(state / "declared-names.txt", names)


def marker_active(marker: str) -> bool:
    from packaging.markers import Marker

    return not marker or Marker(marker).evaluate()


def activate_metadata(state: Path, output: Path) -> None:
    private = json.loads((state / "private-requirements.json").read_text())
    active_private = [
        requirement for requirement in private if marker_active(requirement["marker"])
    ]
    (state / "private-requirements.json").write_text(
        json.dumps(active_private, sort_keys=True), encoding="utf-8"
    )
    write_declared_names(state)
    write_outputs(
        output,
        {"private-dependencies": "true" if active_private else "false"},
    )


def filter_constraints(
    lines: Iterable[str], declared: set[str]
) -> tuple[list[str], list[tuple[str, str]]]:
    kept: list[str] = []
    replaced: list[tuple[str, str]] = []
    for line in lines:
        name = canonical(re.split(r"[=<>!~@ ;\[]", line, maxsplit=1)[0])
        if name in declared:
            replaced.append((name, line))
        else:
            kept.append(line)
    return kept, replaced


def write_base_constraints(state: Path) -> None:
    declared = set((state / "declared-names.txt").read_text().splitlines())
    kept, replaced = filter_constraints(
        (state / "odoo-base-freeze.txt").read_text().splitlines(), declared
    )
    for name, line in replaced:
        print(
            f"::notice title=typecheck environment::{name} is declared by the "
            f"project; the Odoo base selection {line} will not constrain it"
        )
    write_lines(state / "odoo-base-constraints.txt", kept)


def command_detect(args: argparse.Namespace) -> None:
    policy = validate_typecheck_policy(args.policy)
    config_path = Path(".pre-commit-config.yaml")
    config = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    entries, usable_base = changed_entries(args.base, args.head)
    required, reason, mode = typecheck_required(
        enabled=args.enabled == "true",
        precommit_config=config,
        entries=entries,
        usable_base=usable_base,
        layout=args.layout,
        policy=policy,
    )
    values = {
        "required": str(required).lower(),
        "reason": reason,
        "mode": mode,
    }
    if required:
        state = Path(tempfile.mkdtemp(prefix="kernet-typecheck-", dir=args.runner_temp))
        values["state-directory"] = str(state)
    else:
        values["state-directory"] = ""
    values["diff-mode"] = "range" if usable_base else "all-files"
    write_outputs(Path(args.output), values)


def command_collect(args: argparse.Namespace) -> None:
    values = collect_metadata(
        Path.cwd(), Path(args.state_dir), args.layout, args.odoo_version
    )
    write_outputs(Path(args.output), values)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect")
    detect.add_argument("--enabled", choices=("true", "false"), required=True)
    detect.add_argument(
        "--layout", choices=("auto", "project", "addon-group"), default="auto"
    )
    detect.add_argument("--policy", default="strict")
    detect.add_argument("--base", default="")
    detect.add_argument("--head", default="HEAD")
    detect.add_argument("--runner-temp", required=True)
    detect.add_argument("--output", required=True)
    detect.set_defaults(function=command_detect)

    collect = subparsers.add_parser("collect")
    collect.add_argument("--layout", choices=("auto", "project", "addon-group"))
    collect.add_argument("--odoo-version", required=True)
    collect.add_argument("--state-dir", required=True)
    collect.add_argument("--output", required=True)
    collect.set_defaults(function=command_collect)

    fetch = subparsers.add_parser("fetch-private")
    fetch.add_argument("--state-dir", required=True)
    fetch.set_defaults(
        function=lambda args: fetch_private_dependencies(
            Path(args.state_dir), os.environ["DEPENDENCY_TOKEN"]
        )
    )

    materialize = subparsers.add_parser("materialize-private")
    materialize.add_argument("--state-dir", required=True)
    materialize.set_defaults(
        function=lambda args: materialize_private_dependencies(Path(args.state_dir))
    )

    names = subparsers.add_parser("declared-names")
    names.add_argument("--state-dir", required=True)
    names.set_defaults(function=lambda args: write_declared_names(Path(args.state_dir)))

    activate = subparsers.add_parser("activate")
    activate.add_argument("--state-dir", required=True)
    activate.add_argument("--output", required=True)
    activate.set_defaults(
        function=lambda args: activate_metadata(Path(args.state_dir), Path(args.output))
    )

    constraints = subparsers.add_parser("base-constraints")
    constraints.add_argument("--state-dir", required=True)
    constraints.set_defaults(
        function=lambda args: write_base_constraints(Path(args.state_dir))
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.function(args)
    except (TypeError, ValueError) as error:
        raise SystemExit(f"::error title=typecheck environment::{error}") from error


if __name__ == "__main__":
    main()
