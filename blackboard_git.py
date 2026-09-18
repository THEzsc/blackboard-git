"""Local Blackboard snapshot versioning. No credentials or remote repository."""
import argparse
import contextlib
import hashlib
import io
import json
import re
from pathlib import Path
import subprocess
import tempfile
from sync_directory import sync

META = '.blackboard/git-snapshot.json'

def git(root, *args, check=True):
    return subprocess.run(['git', '-C', str(root), *args], check=check, text=True, capture_output=True).stdout.strip()

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def pull(source, destination):
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / '.git').is_symlink():
        raise ValueError('Refusing symlinked Git directory')
    existing = git(root, 'rev-parse', '--show-toplevel', check=False)
    if existing and Path(existing).resolve() != root:
        raise ValueError('Destination is inside another repository')
    if existing and git(root, 'diff', '--cached', '--name-only'):
        raise ValueError('Commit or unstage existing staged changes first')
    metadata = root / META
    if metadata.is_symlink() or (root / '.blackboard').is_symlink():
        raise ValueError('Refusing symlinked metadata')
    old = json.loads(metadata.read_text()) if metadata.exists() else {}
    # Render and validate the entire incoming snapshot before touching the destination.
    with tempfile.TemporaryDirectory(prefix='blackboard-git-') as temporary:
        with contextlib.redirect_stdout(io.StringIO()):
            sync(source, temporary)
        incoming = json.loads((Path(temporary) / '.blackboard/sync-state.json').read_text())
    if old and old['courseId'] != incoming['courseId']:
        raise ValueError('Snapshot belongs to a different course')
    oldfiles = old.get('files', {})
    for rel, info in oldfiles.items():
        p = root / rel
        if not p.resolve().is_relative_to(root) or any(q.is_symlink() for q in [p, *p.parents] if q != root):
            raise ValueError('Unsafe managed path: ' + rel)
        if not p.is_file() or digest(p) != info['sha256']:
            raise ValueError('Local change preserved; restore or move this file before pull: ' + rel)
    if existing and old:
        committed = git(root, 'show', 'HEAD:' + META, check=False)
        if not committed or json.loads(committed) != old:
            raise ValueError('Git snapshot metadata differs from HEAD')
    new = {k: incoming[k] for k in ('courseId', 'files', 'nodes')}
    removed = sorted(set(oldfiles) - set(new['files']))
    with contextlib.redirect_stdout(io.StringIO()):
        sync(source, root)
    for rel in removed:
        (root / rel).unlink()
    # Keep the local navigation page available in fresh clones without timestamp-only commits.
    index = root / '.blackboard/index.html'
    index.write_text(re.sub(r'<p>源快照：.*?</p>', '', index.read_text(), count=1))
    # Remove only obsolete managed folders and only when empty.
    for rel in sorted(set(old.get('nodes', {}).values()) - set(new['nodes'].values()), key=len, reverse=True):
        p = root / rel
        if p.is_dir():
            try:
                p.rmdir()
            except OSError:
                pass
    if not existing:
        git(root, 'init', '-b', 'main')
    # Repository-local exclusions; personal files remain outside automated commits.
    exclude = root / '.git/info/exclude'
    rules = '\n# Blackboard generated metadata\n.DS_Store\n.blackboard/*\n!.blackboard/git-snapshot.json\n!.blackboard/index.html\n'
    if '# Blackboard generated metadata' not in exclude.read_text():
        with exclude.open('a') as f:
            f.write(rules)
    if '!.blackboard/index.html' not in exclude.read_text():
        with exclude.open('a') as f: f.write('\n!.blackboard/index.html\n')
    metadata.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n')
    managed = sorted(set(oldfiles) | set(new['files'])) + [META, '.blackboard/index.html']
    for i in range(0, len(managed), 100):
        git(root, 'add', '-A', '--', *managed[i:i + 100])
    changes = git(root, 'diff', '--cached', '--stat')
    if not changes:
        print('No course changes; no commit created.')
        return
    added = len(set(new['files']) - set(oldfiles))
    changed = sum(oldfiles[k]['sha256'] != new['files'][k]['sha256'] for k in set(oldfiles) & set(new['files']))
    message = f"Blackboard {incoming['courseId']}: +{added} ~{changed} -{len(removed)}"
    git(root, '-c', 'user.name=Blackboard Sync', '-c', 'user.email=blackboard-sync@localhost', 'commit', '-m', message,
        '-m', 'Source snapshot: ' + str(incoming.get('snapshotAt', 'unknown')))
    print(git(root, 'log', '-1', '--format=%h %s'))
    print(changes)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('pull', help='Import a verified exported snapshot and commit course changes')
    p.add_argument('source'); p.add_argument('destination')
    p = commands.add_parser('log'); p.add_argument('destination')
    p = commands.add_parser('diff'); p.add_argument('destination'); p.add_argument('revision', nargs='?', default='HEAD~1')
    args = parser.parse_args()
    if args.command == 'pull':
        pull(args.source, args.destination)
    elif args.command == 'log':
        print(git(args.destination, 'log', '--date=iso', '--format=%h %ad %s'))
    else:
        print(git(args.destination, 'diff', '--stat', args.revision, 'HEAD'))

if __name__ == '__main__':
    main()
