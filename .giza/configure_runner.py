#!/usr/bin/env python3
"""Materialize one protected GitHub configuration secret without printing it."""
import configparser
import json
import os
from pathlib import Path
import tempfile


def main():
    config = json.loads(os.environ['GIZA_VAULT_CONFIG'])
    password, rclone = config['password'], config['rclone_config']
    if not isinstance(password, str) or len(password.strip()) < 24 or not isinstance(rclone, str):
        raise ValueError('Invalid configuration')
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(rclone)
    if ini.sections() != ['giza'] or ini['giza'].get('type') != 'drive' or ini['giza'].get('scope') != 'drive.file':
        raise ValueError('Expected one giza Drive remote using drive.file')
    if not ini['giza'].get('token') or ini['giza'].get('root_folder_id'):
        raise ValueError('Use a fresh app-scoped remote without a foreign root_folder_id')
    root = Path(tempfile.mkdtemp(prefix='giza-private-', dir=os.environ['RUNNER_TEMP']))
    for name, value in [('recovery-password', password), ('rclone.conf', rclone)]:
        path = root / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(value)
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write(f'RESTIC_PASSWORD_FILE={root / "recovery-password"}\n')
        f.write(f'RCLONE_CONFIG={root / "rclone.conf"}\n')
    print('Private runner configuration prepared; no credential values displayed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Vault configuration missing or invalid. No backup started; no credential values displayed.')
        raise SystemExit(1)
