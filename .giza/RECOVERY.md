# Solar Signals vault pilot

Owner approved November 13, 2026; coordination and private receipts: daily-target #115.
This branch adds backup tooling. It does not change the website or certify its claims.
No Drive backup, recurring schedule, owner key custody or independent-AI recovery is
proven just because these files exist.

## Included and missing

Each snapshot contains committed source and tracked media, a complete Git bundle,
two readable Passports, and a SHA-256/byte-count inventory. Working-tree changes,
symlinks, submodules, shallow clones and obvious tracked credential filenames stop
collection. This is a narrow pilot for this public repository, not a general secret
scanner or a backup of every connected service.

An optional locally exported video-script file may be included with --script-export.
The automatic workflow does not export Google Docs. Unexported chats, runtime data,
credentials, Stream masters, the original AI's decisions and unverified live states
are explicitly missing. Never interpret this as the whole business being recoverable.

## Owner setup — keep credentials off the board and out of chat

1. In your password manager, create and save a unique generated password of at least
   24 characters under **Giza Vault — Solar Signals**. The automation needs that
   password too, stored in a protected GitHub secret. Never paste it into an issue,
   chat, command argument, public file or screenshot.
2. On a trusted Mac, install official restic and rclone (for example via Homebrew).
   Configure a fresh rclone remote named **giza**, type **drive**, scope **drive.file**.
   Use your own Google OAuth client per rclone's current Drive documentation and
   complete its normal Google consent flow. Do not choose full-Drive access.
   A token obtained earlier with broader access is not narrowed merely by editing
   the text of the config; use a fresh authorization.
3. App-scoped Drive access sees files made by that OAuth app. The empty folder
   created by the ChatGPT Drive connector is a staging destination and may not be
   visible to rclone. Do not broaden access to reach it. The backup tool will create
   its own **Giza Vault - Solar Signals/restic** path; verify the actual Drive folder
   and record its link privately on #115 before claiming it is the destination.
4. Run `python3 .giza/setup_secret.py` locally from this trusted checkout. It reads
   your saved rclone config and asks for the recovery password without displaying
   it. It sends exactly one configuration bundle to the protected GitHub Actions
   secret **GIZA_VAULT_CONFIG** using authenticated `gh`. No value is printed.
   The approved bundle has two fields: password and rclone_config. Google tokens
   and OAuth client details are inside the latter. Only authorized code should run
   with this secret; public pull requests must never receive it.
5. Set nonsecret repository variable **GIZA_VAULT_PATH** to
   `Giza Vault - Solar Signals/restic`. Leave **GIZA_VAULT_ENABLED** unset until the
   first run and cold recovery have passed. Do not copy private Drive links into
   this public repository.
6. After code review and merge, manually run **Giza encrypted backup and practice
   restore**, with initialize=true only once. Later runs use false. Init failures
   never silently replace or reset an existing repository. Inspect the receipt
   artifact and verify the new encrypted files exist in your Drive.
7. A successful run proves encrypted storage readback and a cold checksum-matched
   restore, not the entire Six-Month-Loss Test. Download a copy using only Drive
   access, restore without the original checkout, run the site and calculator,
   and hand only recovered files to a fresh different AI. Write the scoring
   checklist before the reader receives the files. Until those steps pass, the
   different-AI reading and original nine-check score remain untested.

## Restore without Giza or GitHub

Use official restic/rclone and your saved password plus Google authorization.
Keep the password in a private 0600 file or let restic prompt; do not put it in argv.

    export RESTIC_PASSWORD_FILE=/private/path/recovery-password
    export RCLONE_CONFIG=/private/path/rclone.conf
    restic -r 'rclone:giza:Giza Vault - Solar Signals/restic' snapshots
    restic -r 'rclone:giza:Giza Vault - Solar Signals/restic' check --read-data
    restic -r 'rclone:giza:Giza Vault - Solar Signals/restic' restore SNAPSHOT_ID --target /empty/restore

Locate the restored payload directory containing manifest.json and history.bundle.
Run its recovered project/.giza/vault.py verify against that payload. Then:

    git clone /restored/payload/history.bundle /fresh/project
    git -C /fresh/project checkout SOURCE_COMMIT_FROM_PASSPORT
    python3 -m http.server 8765 --bind 127.0.0.1 --directory /restored/payload/project

Check the restored homepage and media, change calculator inputs and confirm the
results change. Compare the recorded source commit and manifest; a running web
server alone is not proof. Do not execute unknown recovered scripts blindly.
For this known site, `node project/.giza/check_site.mjs project` provides a bounded
calculator/media smoke test. It is not a browser visual review or a security
sandbox for arbitrary customer code.

## Recurrence, retention and custody

After the proof, set GIZA_VAULT_ENABLED=true to enable the daily schedule. This
pilot does not prune/delete snapshots. Retention pruning (14 daily / 8 weekly /
12 monthly) remains a separate reviewed addition; storage can grow until then.
Google Drive is not immutable storage. Deleting the account or both copies can
still lose the work; a folder or Drive trash is not an independent deletion-proof
vault. Losing the recovery password can make the snapshots unusable.

The runner must temporarily decrypt the password to use restic. “Giza never sees
the key” means no key retained by Giza's service or chat, not that the owner's
authorized backup process can operate without it. GitHub retains the protected
secret; Mike retains a recoverable copy in his password manager.

References: https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html
and https://rclone.org/drive/ (especially scopes and OAuth-client setup).
