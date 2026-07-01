# kernet-delivery

Kernet delivery addons.

Kernet addon repository for the **delivery** category, Odoo
**16.0** branch. Branch-per-version, like OCA: each `NN.0`
branch holds the addons for that Odoo major, and CI derives the version from
the branch name.

## Adding an addon

```sh
uvx copier copy gh:kernet-it/addon-template .
```

The scaffold prompts for the name (rendered as `ke_<name>`), folders and
license, and wires the manifest for you.

## How these addons reach production

Projects rendered from `kernet-it/project-template` consume this repo through
`repos.yaml` (git-aggregator), pinned to a commit SHA on this branch. Nothing
deploys from here directly — merge, then bump the pin in the project.

## CI

`ci.yml` calls the shared `kernet-it/kernet-ci` addons workflow: the
pre-commit gate (ruff, ty, pylint-odoo, eslint, prettier, hygiene hooks),
run against a `.venv` built from every addon's
`[tool.kernet.dependencies]` — an import ty can't resolve there is an
undeclared dependency. Install-and-test of the addons is intentionally
disabled for now; pushed code is assumed developer-tested.

## Tooling

`.pre-commit-config.yaml`, `ruff.toml`, `ty.toml`, `.pylintrc`,
`eslint.config.cjs` and `prettier.config.cjs` mirror project-template's dev
tooling. Set up locally with:

```sh
uvx pre-commit install
uv venv && uv pip install <the deps your addons declare>   # ty resolves from ./.venv
```

## Addons

<!-- prettier-ignore-start -->
[//]: # (addons)
[//]: # (end addons)
<!-- prettier-ignore-end -->
