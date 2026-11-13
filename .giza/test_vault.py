#!/usr/bin/env python3
"""Meaningful local failure injection using real restic; never contacts Drive."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('vault', Path(__file__).with_name('vault.py'))
vault = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vault)


class VaultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source'
        cls.source.mkdir()
        # Actual site and media are copied into a separate synthetic Git repository.
        real = Path(__file__).resolve().parents[1]
        for name in ['index.html', 'CNAME', 'media']:
            src, dst = real / name, cls.source / name
            shutil.copytree(src, dst) if src.is_dir() else shutil.copyfile(src, dst)
        cls.git('init')
        cls.git('add', '.')
        cls.git('-c', 'user.name=Local Test', '-c', 'user.email=local-test@example.invalid', 'commit', '-m', 'Synthetic recovery fixture')
        cls.key = cls.root / 'temporary-test-password'
        # No real owner password is generated, read or displayed by this test.
        cls.key.write_bytes(os.urandom(48).hex().encode())
        cls.key.chmod(0o600)
        cls.old_env = os.environ.get('RESTIC_PASSWORD_FILE')
        os.environ['RESTIC_PASSWORD_FILE'] = str(cls.key)
        cls.repo = cls.root / 'restic'
        cls.out = cls.root / 'baseline-receipt'
        cls.receipt = vault.backup(cls.args(cls.out, initialize=True))
        cls.restore = cls.root / 'restore'
        vault.command(['restic', '-r', str(cls.repo), '--no-cache', 'restore', cls.receipt['snapshot_id'], '--target', str(cls.restore)])
        cls.payload = next(p.parent for p in cls.restore.rglob('manifest.json') if (p.parent / 'history.bundle').exists())

    @classmethod
    def tearDownClass(cls):
        if cls.old_env is None:
            os.environ.pop('RESTIC_PASSWORD_FILE', None)
        else:
            os.environ['RESTIC_PASSWORD_FILE'] = cls.old_env
        cls.temp.cleanup()

    @classmethod
    def git(cls, *args):
        return vault.command(['git', *args], cwd=cls.source)

    @classmethod
    def args(cls, out, initialize=False):
        return types.SimpleNamespace(source=cls.source, repository=str(cls.repo), out=out,
                                     initialize=initialize, script_export=None)

    def clone_payload(self, name):
        dest = self.root / name
        shutil.copytree(self.payload, dest)
        return dest

    def test_01_actual_site_media_and_history_restore(self):
        m = vault.verify_restore(self.payload)
        self.assertIn('project/index.html', m['files'])
        self.assertIn('project/media/be-the-future.mp4', m['files'])
        self.assertIn('history.bundle', m['files'])
        self.assertGreater(m['files']['project/media/be-the-future.mp4']['bytes'], 0)
        self.assertEqual(vault.digest(self.payload / 'project/index.html'), vault.digest(self.source / 'index.html'))

    def test_02_local_is_not_claimed_as_cloud_or_full_recovery(self):
        self.assertEqual(self.receipt['result'], 'LOCAL TEST PASSED')
        self.assertFalse(self.receipt['independent_cloud_backup'])
        self.assertEqual(self.receipt['different_ai_reading'], 'NOT TESTED')
        self.assertTrue(any('Video script' in s for s in self.receipt['missing']))

    def test_03_changed_content_fails(self):
        root = self.clone_payload('changed')
        (root / 'project/index.html').write_text('Changed after recovery')
        with self.assertRaises(ValueError): vault.verify_restore(root)

    def test_04_missing_media_fails(self):
        root = self.clone_payload('missing')
        (root / 'project/media/be-the-future.mp4').unlink()
        with self.assertRaises(ValueError): vault.verify_restore(root)

    def test_05_unexpected_files_fail(self):
        root = self.clone_payload('extra')
        (root / 'unexpected').write_text('not in snapshot manifest')
        with self.assertRaises(ValueError): vault.verify_restore(root)

    def test_06_symlink_fails(self):
        root = self.clone_payload('link')
        (root / 'escape').symlink_to(self.key)
        with self.assertRaises(ValueError): vault.verify_restore(root)

    def test_07_dirty_source_fails_and_receipt_is_not_green(self):
        extra = self.source / 'not-committed'
        extra.write_text('test')
        out = self.root / 'dirty-receipt'
        try:
            with self.assertRaises(ValueError): vault.backup(self.args(out))
            self.assertEqual(json.loads((out / 'receipt.json').read_text())['result'], 'FAILED')
        finally:
            extra.unlink()

    def test_08_wrong_key_fails_and_is_not_printed(self):
        wrong = self.root / 'wrong-password'
        wrong.write_text('wrong-test-password-not-an-owner-key')
        wrong.chmod(0o600)
        os.environ['RESTIC_PASSWORD_FILE'] = str(wrong)
        out = self.root / 'wrong-key-receipt'
        try:
            with self.assertRaises(RuntimeError): vault.backup(self.args(out))
            r = json.loads((out / 'receipt.json').read_text())
            self.assertEqual(r['result'], 'FAILED')
            self.assertFalse(r['independent_cloud_backup'])
            self.assertNotIn(wrong.read_text(), (out / 'receipt.json').read_text())
        finally:
            os.environ['RESTIC_PASSWORD_FILE'] = str(self.key)

    def test_09_no_reuse_of_old_success_receipt(self):
        with self.assertRaises(ValueError): vault.backup(self.args(self.out))

    def test_10_insecure_key_file_permissions_rejected(self):
        self.key.chmod(0o644)
        try:
            with self.assertRaises(ValueError): vault.backup(self.args(self.root / 'unsafe-key'))
        finally:
            self.key.chmod(0o600)

    def test_11_invalid_config_does_not_echo_secret(self):
        marker = 'synthetic-sensitive-marker'
        env = dict(os.environ, GIZA_VAULT_CONFIG=marker)
        script = Path(__file__).with_name('configure_runner.py')
        r = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn(marker, r.stdout + r.stderr)

    def test_12_broad_drive_scope_rejected(self):
        env_file = self.root / 'github-env'
        cfg = {'password': 'synthetic-password-only-for-tests',
               'rclone_config': '[giza]\ntype = drive\nscope = drive\ntoken = synthetic\n'}
        env = dict(os.environ, GIZA_VAULT_CONFIG=json.dumps(cfg), RUNNER_TEMP=str(self.root), GITHUB_ENV=str(env_file))
        r = subprocess.run([sys.executable, str(Path(__file__).with_name('configure_runner.py'))], env=env, capture_output=True)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(env_file.exists())

    def test_13_valid_config_writes_private_files_without_values_in_logs(self):
        env_file = self.root / 'github-env-valid'
        password = 'synthetic-password-only-for-tests'
        config = '[giza]\ntype = drive\nscope = drive.file\ntoken = synthetic-token-marker\n'
        env = dict(os.environ, GIZA_VAULT_CONFIG=json.dumps({'password': password, 'rclone_config': config}),
                   RUNNER_TEMP=str(self.root), GITHUB_ENV=str(env_file))
        r = subprocess.run([sys.executable, str(Path(__file__).with_name('configure_runner.py'))], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        for value in (password, 'synthetic-token-marker'):
            self.assertNotIn(value, r.stdout + r.stderr + env_file.read_text())
        entries = dict(line.split('=', 1) for line in env_file.read_text().splitlines())
        for value in entries.values():
            self.assertEqual(Path(value).stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(entries['RESTIC_PASSWORD_FILE']).read_text(), password)

    def test_14_calculator_runs_from_recovered_site(self):
        r = subprocess.run(['node', str(Path(__file__).with_name('check_site.mjs')), str(self.payload / 'project')],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('PASS:', r.stdout)

    def test_15_local_rclone_remote_cannot_claim_cloud_backup(self):
        fake = self.root / 'fake-rclone.conf'
        fake.write_text('[giza]\ntype = local\n')
        fake.chmod(0o600)
        prior = os.environ.get('RCLONE_CONFIG')
        os.environ['RCLONE_CONFIG'] = str(fake)
        args = self.args(self.root / 'fake-cloud-receipt')
        args.repository = 'rclone:giza:fake'
        try:
            with self.assertRaises(ValueError): vault.backup(args)
            self.assertFalse((args.out / 'receipt.json').exists())
        finally:
            if prior is None: os.environ.pop('RCLONE_CONFIG', None)
            else: os.environ['RCLONE_CONFIG'] = prior


if __name__ == '__main__':
    unittest.main(verbosity=2)
