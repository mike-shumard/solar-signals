#!/usr/bin/env python3
"""Owner runs locally. Installs one GitHub secret without revealing credentials."""
import configparser
import getpass
import json
from pathlib import Path
import subprocess
import sys


def main():
    if not sys.stdin.isatty():
        raise ValueError('Run from a private interactive terminal; hidden entry must be available')
    path = Path(input('Path to your private rclone config: ').strip()).expanduser()
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_string(path.read_text())
    if 'giza' not in ini or ini['giza'].get('type') != 'drive' or ini['giza'].get('scope') != 'drive.file':
        raise ValueError('Expected a freshly authorized giza remote with drive.file scope')
    if not ini['giza'].get('token') or ini['giza'].get('root_folder_id'):
        raise ValueError('Use app-created storage without an unrelated root_folder_id')
    # Copy only the authorized remote, never other accounts from the same config.
    narrow = configparser.ConfigParser(interpolation=None)
    narrow['giza'] = dict(ini['giza'])
    import io
    out = io.StringIO()
    narrow.write(out)
    password = getpass.getpass('Saved recovery password (hidden): ')
    if len(password.strip()) < 24 or password != getpass.getpass('Confirm recovery password (hidden): '):
        raise ValueError('Password is too short or does not match')
    if input('Have you saved this password in your password manager? Type YES: ').strip() != 'YES':
        raise ValueError('Save the recovery password before setting up automation')
    data = json.dumps({'password': password, 'rclone_config': out.getvalue()}).encode()
    result = subprocess.run(['gh', 'secret', 'set', 'GIZA_VAULT_CONFIG', '--repo', 'mike-shumard/solar-signals'],
                            input=data, capture_output=True)
    if result.returncode:
        raise RuntimeError('GitHub rejected the protected secret write; check gh authentication locally')
    print('Protected GIZA_VAULT_CONFIG installed. No credential values displayed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Setup did not complete. No credentials printed. Check local configuration and gh access.')
        raise SystemExit(1)
