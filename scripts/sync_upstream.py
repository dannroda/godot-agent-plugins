"""Copia al marketplace las entradas de awesome-gamedev-agent-skills que sirven para Godot.

Las skills no se copian: cada entrada apunta al repo de ellos, así que se instalan desde ahí y
reciben sus actualizaciones. Lo que se copia es la lista de skills de cada plugin, porque el repo
no tiene plugin.json propio. Correr de nuevo cuando agreguen o renombren skills:

    python3 scripts/sync_upstream.py [ruta a un clon de awesome-gamedev-agent-skills]
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = 'gamedev-skills/awesome-gamedev-agent-skills'
PLUGINS = ['godot', 'disciplines', 'genres', 'workflows']
MARKETPLACE = os.path.join(os.path.dirname(__file__), '..', '.claude-plugin', 'marketplace.json')


def upstream_entries(clone):
    with open(os.path.join(clone, '.claude-plugin', 'marketplace.json')) as f:
        plugins = {p['name']: p for p in json.load(f)['plugins']}
    entries = []
    for name in PLUGINS:
        p = plugins[name]
        entries.append({
            'name': name,
            'source': {'source': 'github', 'repo': REPO},
            'description': p['description'] + ' From awesome-gamedev-agent-skills (Apache 2.0), installed from its repo.',
            'author': {'name': 'awesome-gamedev-agent-skills contributors'},
            'homepage': 'https://github.com/' + REPO,
            'license': 'Apache-2.0',
            'category': 'development',
            'strict': False,
            'skills': p['skills'],
        })
    return entries


def main():
    if len(sys.argv) > 1:
        clone = sys.argv[1]
    else:
        clone = tempfile.mkdtemp()
        subprocess.run(['git', 'clone', '-q', '--depth', '1', 'https://github.com/' + REPO, clone], check=True)
    with open(MARKETPLACE) as f:
        marketplace = json.load(f)
    own = [p for p in marketplace['plugins'] if isinstance(p['source'], str)]
    marketplace['plugins'] = own + upstream_entries(clone)
    with open(MARKETPLACE, 'w') as f:
        json.dump(marketplace, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('plugins:', ', '.join(p['name'] for p in marketplace['plugins']))


main()
