# Contributing

Issues and pull requests are welcome: a wrong engine fact, a pattern that misleads, a missing trap, or a new skill.

- One plugin per topic under `plugins/<name>/`, with `.claude-plugin/plugin.json` and `skills/<skill>/SKILL.md` (plus `references/` for the long parts). List a new plugin in `.claude-plugin/marketplace.json`.
- A skill's `description` says when to use it; keep `SKILL.md` short and move detail to `references/`.
- Engine facts must hold on the Godot versions the skill names. Say how you checked them (a project, a headless run, the docs page).
- Don't paste text or code from books, courses or other skills. Cite them by title, chapter and page.
- Run `claude plugin validate .` and `claude plugin validate plugins/<name>` before opening the PR. CI runs the same checks.
- The `godot`, `disciplines`, `genres` and `workflows` entries point at awesome-gamedev-agent-skills. Don't edit them by hand: run `python3 scripts/sync_upstream.py` when that repo adds or renames skills. Fixes to those skills go to that repo.
- Bump `version` in the plugin's `plugin.json` and its marketplace entry when its skills change, so installed copies update.
