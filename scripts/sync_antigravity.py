"""Escribe el manifiesto de Antigravity de cada plugin a partir del de Claude Code.

Antigravity carga como plugin una carpeta con .antigravity-plugin/plugin.json y skills/<skill>/SKILL.md,
así que las mismas skills sirven para los dos agentes. Este script copia de .claude-plugin/plugin.json
los campos que los dos entienden (name, description, version, author, homepage, repository) y deja
los que son solo de Antigravity (displayName, suggestedPrompts, logo) como estén.

    python3 scripts/sync_antigravity.py           # actualiza los manifiestos
    python3 scripts/sync_antigravity.py --check   # falla si alguno está desactualizado (CI)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ("name", "description", "version", "author", "homepage", "repository")
ORDER = ("name", "displayName", "description", "version", "author", "homepage", "repository", "logo", "suggestedPrompts")


def expected(plugin: Path) -> tuple[Path, str]:
    claude = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())
    target = plugin / ".antigravity-plugin" / "plugin.json"
    current = json.loads(target.read_text()) if target.exists() else {}
    merged = {k: v for k, v in current.items() if k not in SHARED}
    merged.update({k: claude[k] for k in SHARED if k in claude})
    unknown = sorted(set(merged) - set(ORDER))
    if unknown:
        # Antigravity descarta en silencio los campos que no conoce.
        sys.exit(f"{target.relative_to(ROOT)}: campos que Antigravity ignora: {', '.join(unknown)}")
    ordered = {k: merged[k] for k in ORDER if k in merged}
    return target, json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    check = "--check" in sys.argv[1:]
    stale = []
    for plugin in sorted((ROOT / "plugins").iterdir()):
        if not (plugin / ".claude-plugin" / "plugin.json").exists():
            continue
        target, text = expected(plugin)
        if target.exists() and target.read_text() == text:
            continue
        stale.append(str(target.relative_to(ROOT)))
        if not check:
            target.parent.mkdir(exist_ok=True)
            target.write_text(text)
    if check and stale:
        sys.exit("Desactualizados (correr python3 scripts/sync_antigravity.py): " + ", ".join(stale))
    for path in stale:
        print("actualizado", path)


if __name__ == "__main__":
    main()
