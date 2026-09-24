# kernet-delivery

Kernet delivery addons.

Kernet addon repository for the **delivery** category, Odoo
**17.0** branch. Branch-per-version, like OCA: each `NN.0`
branch holds the addons for that Odoo major, and CI receives the complete
series from this render.

## Adding an addon

```sh
uvx copier copy gh:kernet-it/addon-template .
```

The scaffold prompts for the name (rendered as `ke_<name>`), folders and
license, and wires the manifest for you.

## Releasing addon changes

This public repository keeps the manual release contract. Kbot, the Kernet release
bot, does not serve public repositories.

A functional change to an addon increases its canonical
`17.0.x.y.z` version in `__manifest__.py` and adds that same
version as the first entry in `readme/HISTORY.rst`. The developer commits both
files; CI validates them and does not modify the branch. Changes limited to
`README*`, `readme/`, `doc/`, `docs/`, tests, `static/description/`, or Copier
metadata do not require a release.

Existing short versions such as `1.0` and `1.0.0` remain valid base versions.
CI normalizes them before comparison, so changing `1.0.0` only to
`17.0.1.0.0` is not an increase. An existing addon creates its
history file the first time it has a functional change; no historical backfill
is required. If legacy base metadata cannot be compared, that first change
adopts a canonical proposed version; the proposed manifest must still match
this branch's Odoo series.

`addon-template` generates a release note fragment in `readme/newsfragments/` for
a new addon. This repository does not use fragments: delete it and write the
initial entry in `readme/HISTORY.rst`.

## How these addons reach production

Customer projects select a revision of this repository in their addon dependency
configuration. A merge here does not deploy a customer project; update and validate
the consuming project separately.

## CI

`ci.yml` calls the shared `kernet-it/kernet-ci` addons workflow: the addon release
check, the ordinary pre-commit gate (rstcheck, ruff, pylint-odoo, eslint, prettier
and hygiene hooks), and the manual-stage ty hook. CI runs ty against a `.venv` built
from every addon's `[tool.kernet.dependencies]` — an import ty can't resolve there is
an undeclared dependency. Install-and-test of the addons is intentionally disabled
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
