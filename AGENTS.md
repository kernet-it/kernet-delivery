# Repository instructions

This repository contains Kernet addons for Odoo 20.0. Keep this
series on its matching numeric branch. Addons live directly below the root.
Preserve the generated addon-table markers in README.md.

## Documentation

Write repository and addon READMEs, functional documentation and release notes in
Spanish. Write technical documentation and agent instructions in English. Add an
English README translation only when needed, link it from the Spanish source, and
update it when the source changes.

Keep the repository README focused on purpose, available addons, supported Odoo
series and links. Keep each addon README.rst short: introduction, requirements,
minimum configuration and first steps. Put detailed workflows in
`docs/functional/` and architecture, extension points, integrations and upgrade
requirements in `docs/technical/`, relative to the repository or addon concerned.
Use Markdown for detailed documentation and RST for addon READMEs. Keep
`readme/HISTORY.rst` for release history.

Each fact has one authoritative home; link to it instead of copying it. Update
affected documentation with the behavior it describes. Add only useful pages;
do not leave empty sections or invented behavior in a completed addon.

## Functional documentation ownership

Kernet consultants own and maintain `docs/functional/`. Developers and AI agents
can write an initial guide and document new or changed configuration and workflows
as part of the corresponding change. Read the existing guide before editing it.
Preserve accurate consultant content, examples and explanations. Change existing
content when verified behavior makes it inaccurate; update the affected passages
and retain material that still applies. Do not replace or shorten a guide to match
the README's brevity. Flag uncertain business details for consultant review rather
than inventing them.

Functional guides explain why a process exists, who uses it, where to configure or
perform it, how each step works and what result to expect. Describe prerequisites,
permissions, configuration choices and their differences, consequences, examples
and troubleshooting where relevant. Keep the README short and link to this detail.

## Agent instructions

This AGENTS.md is the authoritative instruction source at this scope. CLAUDE.md
imports it. Keep shared rules here; addon AGENTS.md files contain local constraints
and documentation routes. Read the relevant addon's instructions before editing it.
Keep machine-specific notes and secrets out of tracked instructions.

## Development and releases

Read [the technical guide](docs/technical/README.md) for setup, validation and
release requirements. Use the matching Odoo framework guidance. Keep changes
within the requested scope and preserve unrelated work. A static CI pass does not
prove addon installation or runtime behavior; report the validation actually run.

A functional addon change increases the manifest version and adds the same version
at the top of `readme/HISTORY.rst`.
