#!/usr/bin/env python3
"""One-project restic backup and cold restore. Never sends mail or deploys."""
import argparse
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone


def command(args, *, cwd=None, env=None):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=1800)
    if result.returncode:
        # Tool stderr can contain environment-specific details. Do not echo it.
        raise RuntimeError(f"{Path(args[0]).name} operation failed (exit {result.returncode}); no success receipt issued")
    return result.stdout


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(root):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symbolic links are outside this pilot scope')
        if path.is_file() and path != root / 'manifest.json':
            files[path.relative_to(root).as_posix()] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    return files


def verify_restore(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    expected = manifest['files']
    if not expected or inventory(root) != expected:
        raise ValueError('Restored file inventory or checksum differs; recovery NOT verified')
    # A valid bundle is necessary to recover history, not just the current page.
    with tempfile.TemporaryDirectory() as tmp:
        command(['git', 'init', '--bare', tmp])
        command(['git', '-C', tmp, 'bundle', 'verify', str((root / 'history.bundle').resolve())])
    return manifest


def build_payload(source, target, script_export=None):
    source = source.resolve()
    if command(['git', 'status', '--porcelain'], cwd=source).strip():
        raise ValueError('Commit or remove working-tree changes before taking a reproducible backup')
    shallow = command(['git', 'rev-parse', '--is-shallow-repository'], cwd=source).decode().strip()
    if shallow == 'true':
        raise ValueError('Full Git history required; fetch with depth 0 before backup')
    commit = command(['git', 'rev-parse', 'HEAD'], cwd=source).decode().strip()
    tracked = command(['git', 'ls-tree', '-r', 'HEAD'], cwd=source).decode().splitlines()
    for row in tracked:
        mode, _, _ = row.partition(' ')
        path = row.split('\t', 1)[1]
        if mode in ('120000', '160000'):
            raise ValueError('Symlinks and submodules require a separate collection policy')
        if re.search(r'(^|/)(\.env(?:\..*)?|rclone\.conf|.*\.(?:pem|key))$', path, re.I):
            raise ValueError('Potential credential file tracked; inspect and remove it before backup')
    target.mkdir()
    project = target / 'project'
    project.mkdir()
    archive = command(['git', 'archive', '--format=tar', commit], cwd=source)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(project, filter='data')
    command(['git', 'bundle', 'create', str((target / 'history.bundle').resolve()), '--all', 'HEAD'], cwd=source)
    missing = [
        'Private ChatGPT/Claude/Muse conversations: not exported or collected.',
        'Railway runtime, volumes, credentials and Cloudflare Stream masters: not collected.',
        'Giza nine-check score: not independently rechecked by this backup routine.',
        'Different-AI recovery reading: pending a fresh reader and prewritten checklist.',
    ]
    if script_export:
        export = Path(script_export)
        if export.is_symlink() or not export.is_file():
            raise ValueError('Script export must be a regular local file')
        (target / 'documents').mkdir()
        shutil.copyfile(export, target / 'documents' / ('video-script' + export.suffix))
    else:
        missing.append('Video script Google Doc: not exported or collected.')
    passport = {
        'schema': 'giza-passport-pilot-v1', 'project': 'Solar Signals',
        'purpose': 'Public solar information site with an illustrative savings calculator.',
        'source_commit': commit, 'collected_at': datetime.now(timezone.utc).isoformat(),
        'state': 'Collected; destination, integrity and restore status require a separate run receipt.',
        'completed': ['Committed source, tracked media and complete fetched Git history collected.'],
        'independently_verified': [],
        'decisions': ['Owner approved the one-project encrypted Drive pilot on 2026-11-13 (#115).',
                      'Preserve existing website content; backup implementation is not a content audit.'],
        'locations': {'code': 'project/', 'history': 'history.bundle', 'inventory': 'manifest.json'},
        'protected_outside_ai': 'Not established by this Passport alone; see completed run receipt.',
        'missing': missing, 'failures_and_recoveries': [],
        'continue': ['Verify manifest.json with vault.py verify.',
                     'Clone history.bundle into a fresh folder and checkout source_commit.',
                     'Serve project/ locally with python3 -m http.server; test the calculator.'],
    }
    (target / 'PASSPORT.json').write_text(json.dumps(passport, indent=2) + '\n')
    lines = ['# Solar Signals — recovery Passport', '', f'Collected commit: `{commit}`', '',
             'This describes collected material, not a claim of a completed cloud backup.', '']
    for key, value in passport.items():
        lines.extend([f'## {key.replace("_", " ").title()}', json.dumps(value, indent=2), ''])
    (target / 'PASSPORT.md').write_text('\n'.join(lines))
    manifest = {'schema': 'giza-inventory-v1', 'source_commit': commit, 'files': inventory(target)}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest, passport


def backup(args):
    key = Path(os.environ.get('RESTIC_PASSWORD_FILE', ''))
    if not key.is_file() or key.is_symlink() or stat.S_IMODE(key.stat().st_mode) & 0o077:
        raise ValueError('RESTIC_PASSWORD_FILE must be an owner-readable private file (mode 600)')
    if not key.read_bytes().strip():
        raise ValueError('Recovery password file is empty')
    repo = args.repository
    if not (Path(repo).is_absolute() or re.fullmatch(r'rclone:giza:[A-Za-z0-9 _./-]+', repo)):
        raise ValueError('Pilot accepts an absolute local repository or rclone:giza: path only')
    if repo.startswith('rclone:') and not os.environ.get('RCLONE_CONFIG'):
        raise ValueError('RCLONE_CONFIG is required for Drive')
    env = dict(os.environ)
    if repo.startswith('rclone:'):
        config_path = Path(env['RCLONE_CONFIG']).resolve()
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(config_path.read_text())
        allowed = {'type', 'scope', 'token', 'client_id', 'client_secret'}
        if (config.sections() != ['giza'] or config['giza'].get('type') != 'drive'
                or config['giza'].get('scope') != 'drive.file'
                or not config['giza'].get('token') or set(config['giza']) - allowed):
            raise ValueError('Cloud claims require the app-scoped Google Drive backend, not an alias or local remote')
        if stat.S_IMODE(config_path.stat().st_mode) & 0o077:
            raise ValueError('Rclone configuration must be private (mode 600)')
        # Environment overrides must not change this verified remote into another backend.
        for name in list(env):
            if name.startswith('RCLONE_'):
                env.pop(name)
        env['RCLONE_CONFIG'] = str(config_path)
    for name in ('RESTIC_PASSWORD', 'RESTIC_PASSWORD_COMMAND', 'RESTIC_REPOSITORY', 'RESTIC_REPOSITORY_FILE'):
        env.pop(name, None)
    env['RESTIC_PASSWORD_FILE'] = str(key.resolve())
    args.out.mkdir(parents=True, exist_ok=True)
    receipt_path = args.out / 'receipt.json'
    # Never leave a prior success receipt representing a new failed attempt.
    if receipt_path.exists():
        raise ValueError('Use a new empty output directory for each run')
    receipt = {'schema': 'giza-vault-receipt-v1', 'result': 'FAILED',
               'started_at': datetime.now(timezone.utc).isoformat(),
               'storage': 'google-drive-via-rclone' if repo.startswith('rclone:') else 'local-test-only',
               'independent_cloud_backup': False, 'different_ai_reading': 'NOT TESTED'}
    try:
        with tempfile.TemporaryDirectory(prefix='giza-vault-') as tmp:
            work = Path(tmp)
            payload = work / 'payload'
            manifest, passport = build_payload(args.source, payload, args.script_export)
            receipt['source_commit'] = manifest['source_commit']
            receipt['missing'] = passport['missing']
            base = ['restic', '--repo', repo, '--no-cache']
            if args.initialize:
                command(base + ['init'], env=env)
            output = command(base + ['backup', '--json', '--host', 'giza-solar-signals',
                                     '--tag', 'giza-pilot', 'payload'], cwd=work, env=env)
            summary = [json.loads(line) for line in output.splitlines() if line.strip()]
            summary = [row for row in summary if row.get('message_type') == 'summary']
            if len(summary) != 1 or not re.fullmatch(r'[0-9a-f]{8,64}', summary[0].get('snapshot_id', '')):
                raise ValueError('No unique snapshot receipt returned')
            snapshot = summary[0]['snapshot_id']
            receipt['snapshot_id'] = snapshot
            command(base + ['check', '--read-data'], env=env)
            receipt['integrity_check'] = 'PASS: restic check --read-data'
            restored = work / 'cold-restore'
            command(base + ['restore', snapshot, '--target', str(restored)], env=env)
            candidates = list(restored.rglob('manifest.json'))
            roots = [p.parent for p in candidates if (p.parent / 'history.bundle').is_file()]
            if len(roots) != 1:
                raise ValueError('Restore must contain exactly one recovery payload')
            recovered = verify_restore(roots[0])
            if recovered != manifest:
                raise ValueError('Restored manifest does not match the collected manifest')
            receipt['restore_comparison'] = 'PASS: exact file set, byte lengths and SHA-256 hashes'
            receipt['verified_file_count'] = len(manifest['files'])
            receipt['manifest_sha256'] = digest(payload / 'manifest.json')
            receipt['independent_cloud_backup'] = repo.startswith('rclone:')
            receipt['result'] = 'RESTORE VERIFIED' if repo.startswith('rclone:') else 'LOCAL TEST PASSED'
            # Human-readable public-safe receipts; no secrets or private document text.
            (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            (args.out / 'PASSPORT.md').write_text((payload / 'PASSPORT.md').read_text())
    finally:
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
        (args.out / 'digest-draft.txt').write_text(
            'DRAFT — NOT SENT\nSubject: Solar Signals backup test\n\n'
            f'Result: {receipt["result"]}.\n'
            f'Independent cloud backup verified: {receipt["independent_cloud_backup"]}.\n'
            'Different-AI recovery reading: not tested. Full loss-recovery demonstration remains incomplete.\n'
            'See receipt.json for snapshot, source version, verification and missing items.\n')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    b = sub.add_parser('backup')
    b.add_argument('--source', type=Path, default=Path('.'))
    b.add_argument('--repository', required=True)
    b.add_argument('--out', type=Path, required=True)
    b.add_argument('--initialize', action='store_true', help='Only for a brand-new repository; never automatic')
    b.add_argument('--script-export')
    v = sub.add_parser('verify')
    v.add_argument('restored_payload', type=Path)
    args = p.parse_args()
    try:
        if args.mode == 'verify':
            m = verify_restore(args.restored_payload)
            print(json.dumps({'result': 'PASS', 'verified_file_count': len(m['files'])}))
        else:
            print(json.dumps(backup(args)))
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        print(f'Giza vault did not complete: {type(exc).__name__}. No protection claim issued.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
