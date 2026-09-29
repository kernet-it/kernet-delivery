# kernet-delivery

Kernet delivery addons.

Kernet addon repository for the **delivery** category, Odoo
**20.0** branch. Branch-per-version, like OCA: each `NN.0`
branch holds the addons for that Odoo major, and CI receives the complete
series from this render.

## Adding an addon

```sh
uvx copier copy gh:kernet-it/addon-template .
```

The scaffold prompts for the name (rendered as `ke_<name>`), folders and
license, and wires the manifest for you. Then add the addon to the workspace with
`uv run --script .github/scripts/addon_pyproject.py --write` (see below).

## Addon packages

Each addon is a Python package, `odoo-addon-<addon>`, that
[whool](https://github.com/sbidoul/whool) builds from the manifest, as OCA does.
`<addon>/pyproject.toml` holds only what the manifest cannot give:

```toml
[build-system]
requires = ["whool"]
build-backend = "whool.buildapi"

[project]
name = "odoo-addon-ke_thing"
requires-python = ">=3.12"
dynamic = ["version", "dependencies", "description", "readme", "license", "authors", "classifiers", "urls"]

[tool.uv.sources]
odoo-addon-ke_sibling = { workspace = true }
```

whool writes the rest when it builds the package:

- The version is the manifest `version`. On a commit after the last change of that
  version, whool adds the number of commits that changed the addon since then, for
  example `20.0.1.2.0.3`. whool reads the Odoo series from the start
  of the version. A short legacy version, such as `1.0` or `1.0.1`, names no series;
  Odoo and the release check read it as a version of this branch, and a manifest
  without a version as `1.0`. For such an addon the script writes
  `odoo_series_override = "20.0"` in `[tool.whool]`, so that whool
  builds the package for 20.0. The package version stays the short
  version, such as `1.0.1`, and a manifest without a version gives `0.0.0`, until the
  first release of the addon by kbot writes the full `20.0.x.y.z` version. The
  version range that other addons require for this addon does not accept a short
  version; in this workspace their `workspace` source replaces the range. With a full
  version, `--write` removes the key. The check accepts a key of this series that
  stays next to a full version, because the release commit of kbot does not run the script;
  a key of another series fails the check.
- The dependencies are `odoo==20.0.*`, then
  `odoo-addon-<name>==20.0.*` for each addon in
  `depends` that is not an Odoo core addon, then each name of
  `external_dependencies["python"]` as it is. Write distribution names there, such as
  `python-dateutil`, not import names. To add a version specifier or to replace a
  name, use `external_dependencies_override` in `[tool.whool]`.
- The summary, the license, the author, the website and the README come from the
  manifest and the addon README.

whool does not read `requires-python`: uv uses it for the workspace only. The wheel has
no Python bound for 20.0; the Odoo dependency sets it, and the image of
a project sets the interpreter.

The script `.github/scripts/addon_pyproject.py` owns the three tables above, the key
`odoo_series_override` of `[tool.whool]`, and the `members` of the root
`pyproject.toml`: the list of addons. It edits TOML with tomlkit, so every other
table, key and comment stays, such as the other keys of `[tool.whool]` or
`[tool.kernet.dependencies]`. The pre-commit hook `addon-pyproject` runs it on each
commit and in the changed-file gate of CI, also for a commit that only deletes
files. It fails when an addon has no `pyproject.toml`, when its tables differ from the
manifest (a new sibling in `depends` needs its `workspace` source), or when `members`
is not the list of addons. Then write them:

```sh
uv run --script .github/scripts/addon_pyproject.py --write
```

The script needs tomlkit. The hook runs it with the tomlkit that pre-commit installs
in the hook environment, from `additional_dependencies`; by hand, `uv run --script`
installs the version that the inline metadata of the script names. Both keep the same
pin. On a machine or a CI runner with an empty cache, the first run of either
downloads tomlkit from the package index, as each other hook does.

The release check counts `<addon>/pyproject.toml` as a part of the addon: a change to
it is a release of the addon, with a `misc` fragment.

## Development environment

`pyproject.toml` at the root makes the repository a
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): each addon is a
member, and the `dev` dependency group adds Odoo and the tools. Then:

```sh
uv sync                  # .venv with Odoo, the dependencies of each addon, ruff and ty
uvx ty@0.0.63 check      # ty reads .venv, also for odoo.addons.*
.venv/bin/odoo --addons-path=. -d <database> -i <addon> --stop-after-init
.venv/bin/odoo --addons-path=. -d <database> -u <addon> --test-enable \
  --test-tags=/<addon> --stop-after-init
```

`uv sync` installs the dependencies of each addon, but not the addon:
`[tool.uv] package = false` in `<addon>/pyproject.toml` says so, and a project that
takes the addon from Git still installs it. Odoo takes the addons from the checkout,
so give it `--addons-path=.`. An editable install would not do: the editable build of
whool links `<addon>/build/__editable__/odoo/addons/<addon>` back to the addon, and
Odoo follows that link without end when it scans the files of the addon, for example
for the JavaScript bundles before the browser tests ("Failed to initialize
database"). A checkout that `uv sync` made with an earlier template still has these
links: delete them once with `rm -rf */build`.

ty resolves `odoo.addons.*` only for the addons in the Odoo package: Odoo adds the other
addons to that namespace at run time, which ty does not follow, so `ty.toml` lets
`odoo.addons.**` stay unresolved, and ty does not report a misspelled import of an
addon of this repository or of another one.

The environment follows the branch, and the repository has no lock: `uv.lock` is
ignored. Odoo comes from the nightly source archive of the 20.0 branch,
not from a dated archive or a checksum: this repository follows the tip of its
series (odoo-oci, PR18), and a project keeps the exact pins. So two runs of CI can
use different builds of Odoo; `.venv/bin/odoo --version` names the one of a run.
Odoo puts its core addons into the package only in its source archives: a package
built from Git has no data files for the addons outside `odoo/addons`, so Odoo cannot
install `web` from it. Each other addon comes at its latest release on PyPI. A local
`uv.lock` keeps those versions until you run `uv sync --upgrade`. CI has no lock and
resolves again on each run. A personal uv setting such as `exclude-newer` also
applies, so your environment can be older than the one of CI.

The root has no `[tool.uv.sources]` on purpose. When a project takes an addon of
this repository from Git, uv reads the root of this workspace too, and a source there
would conflict with the pins of that project, Odoo first. So a package that does not
come from PyPI is a direct reference in the `git` dependency group at the end of the
root `pyproject.toml`, which only this repository reads:

```toml
git = [
    "odoo-addon-ke_base_thing @ git+https://github.com/kernet-it/kernet-base@20.0#subdirectory=ke_base_thing",
]
```

Add an entry when an addon here depends on an addon of another Kernet repository, or
on an OCA addon that OCA has not published for 20.0. A project that uses
these addons gives its own source for each such package.

The Kernet repositories are private. uv fetches them with Git, so your Git
credentials apply. With SSH, rewrite the address once:

```sh
git config --global url."git@github.com:kernet-it/".insteadOf "https://github.com/kernet-it/"
```

With the GitHub CLI, `gh auth setup-git` is enough. A CI job that syncs this
environment needs a token of the Kernet CI App for that one step only, given as
`GIT_CONFIG_*` variables that rewrite the same address to
`https://x-access-token:<token>@github.com/kernet-it/`, so that the token is in no
file and in no cache.

## Releasing addon changes

Kbot, the Kernet release bot, prepares addon releases from Towncrier fragments.
[kbot `docs/kbot.md`](https://github.com/kernet-it/kbot/blob/main/docs/kbot.md)
is the authoritative contract.

### Release notes

For each functional change, add a Spanish fragment in each addon that it changes:

```text
<addon>/readme/newsfragments/<id>.<type>.rst
```

Use the pull request number or a short descriptive slug as the ID. Kbot consumes
only fragments that the pull request adds, so do not reuse a fragment that is already
on the target branch. The types are:

- `feature`: new or changed behavior.
- `bugfix`: a correction.
- `removal`: removed behavior or an incompatible change.
- `misc`: other changes.

For example, `ke_sales/readme/newsfragments/245.bugfix.rst`:

```rst
Evita duplicar la factura al confirmar el pedido dos veces.
```

This applies also when the addon already has a fragment in the pull request: kbot
releases all fragments of a pull request together, one note each.
Kbot checks only for one new fragment in each changed addon, so it does not find a
change without its own note. An internal change, such as a rename for a linter, gets
a `misc` fragment. Two fragments of the same type in one addon need different IDs;
use a slug for each.

Write each note for the client: describe the effect, not the code. Describe an
internal change without a visible effect in general terms, such as
`Ajustes internos de calidad del código.`

Keep each note brief. Put detailed Spanish instructions in `docs/functional/` and
English implementation details in `docs/technical/`.

Do not change the manifest version or an existing `readme/HISTORY.rst`. Kbot
increases the version, adds the notes at the top of `readme/HISTORY.rst` and
deletes the consumed fragments. A new addon needs a fragment and a canonical
`20.0.x.y.z` version, but no `readme/HISTORY.rst`: kbot keeps the
initial version and creates the history file. `addon-template` generates both.

Changes limited to `README*`, `readme/`, `doc/`, `docs/`, tests,
`static/description/`, `AGENTS.md`, `CLAUDE.md` or Copier metadata are not
functional and need no fragment. Kbot rejects fragments in an addon without a
functional change.

### Preparation and merge

Pull request CI validates the fragment format and the code. It does not require a new
version. The required `kbot/release` status stays expected until kbot verifies the
release.

This public repository cannot run the validation of kbot in CI. Before the release
commit, CI checks only the format of new fragments: the file name and type, and a
nonempty file of at most 16 KiB. Kbot checks the other rules above when you post
`@kbot plan` or `@kbot merge`, for example a missing fragment or a changed version.
CI also does not lint the manifests and histories that kbot will write. If they fail
the lint after kbot adds its release commit, revert that commit, correct the fragments
and add a new command.

When the pull request is ready, a maintainer with write, maintain or admin access
adds a new comment:

```text
@kbot merge patch
@kbot merge minor ke_stock=major
@kbot status
@kbot cancel
```

- `merge LEVEL` applies the level to each affected addon. `addon=LEVEL` overrides
  the level for that affected addon only.
- `patch` increases the fifth version component, `minor` the fourth and `major` the
  third. Lower components go back to zero: `minor` changes
  `20.0.2.3.4` to `20.0.2.4.0`. Kbot converts short
  legacy versions such as `1.0` to the canonical form first.
- `nobump` is only for pull requests without functional addon changes. Every pull
  request needs a `@kbot merge` command, also one that changes no addon (CI, tooling
  or repository documentation) or only the documentation, tests or agent
  instructions of an addon. Such a pull request needs no fragment; use
  `@kbot merge nobump`. Kbot accepts any level when no addon is affected.
- `status` shows the recorded phase of the request. `cancel` stops the active
  request; a release commit that kbot added stays on the pull request.

Kbot rejects unknown addon names, duplicate overrides and edited comments. To change
a command, add a new comment. If kbot does not answer, add `@kbot status` again.

The pull request must be open, ready for review, from a branch of this repository
and up to date with its target. When an addon needs a release, kbot adds one release
commit to the original pull request; otherwise it adds no commit. Then CI and the
required approvals must pass, and kbot merges with GitHub's normal merge commit.
Kbot does not approve pull requests or bypass rules. If the pull request changes
`.github/workflows/`, kbot prepares and verifies the release, but a maintainer does
the final normal merge.

Do not push to the pull request while kbot works on it. If the head or the target
changes after the command, the request stops. Remove the release commit, update the
branch with its target, resolve conflicts and add a new command.

Kbot does not support pull requests from forks, merge queues, or promotion pull
requests that already contain releases, such as a merge of one long-lived branch
into another. For these, create a branch of this repository from the target, apply
the code changes without the generated release metadata, add new fragments and
follow the normal process.
See [kbot `docs/kbot.md`](https://github.com/kernet-it/kbot/blob/main/docs/kbot.md).

### Enrollment

Kbot serves this public repository through the private `kernet-it/kbot-relay`
repository, only after an operator enrolls it: the relay forwarder
`.github/workflows/kbot.yml` with its App secrets, the SQLite journal, the
`Require kbot release preparation` ruleset and the relay target. Before enrollment,
commands get no answer. Enroll a new version branch before its first release, and do
not merge addon changes before enrollment: CI accepts their fragments, but nothing
prepares the release, and kbot cannot consume fragments that are already on the target
branch. The procedure is in the README of `kernet-it/kbot-relay` and in
[kbot `docs/kbot.md`](https://github.com/kernet-it/kbot/blob/main/docs/kbot.md).

## How these addons reach production

Customer projects select a revision of this repository in their addon dependency
configuration. A merge here does not deploy a customer project; update and validate
the consuming project separately.

## CI

`ci.yml` calls the shared `kernet-it/kernet-ci` addons workflow: the addon release
check, the ordinary pre-commit gate (rstcheck, ruff, pylint-odoo, eslint, prettier
and hygiene hooks), and the manual-stage ty hook. CI runs ty against a `.venv` built
from every addon's `[tool.kernet.dependencies]` — an import ty can't resolve there is
an undeclared dependency. The environment of `uv sync` above does not replace it in
CI yet. Install-and-test of the addons is intentionally disabled
for now; pushed code is assumed developer-tested.

## Tooling

`.pre-commit-config.yaml`, `ruff.toml`, `ty.toml`, `.pylintrc`,
`eslint.config.cjs` and `prettier.config.cjs` mirror project-template's dev
tooling. Set up locally with:

```sh
uvx pre-commit install
```

The installed commit hook runs the ordinary checks automatically. ty needs a prepared
Odoo environment, so the required CI job owns that check for this repository layout.
