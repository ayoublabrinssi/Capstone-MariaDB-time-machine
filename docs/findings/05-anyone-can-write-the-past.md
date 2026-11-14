# 5. Anyone who can write can write the past

**In one sentence.** On a default server, a user with nothing more than `INSERT` and `UPDATE` can add a version dated 2015 or make a change dated 2030; only `secure_timestamp=YES` stops it, and that also stops any import, so the safe order is "load first, lock after".

[← All findings](README.md)

## The idea

System versioning is often sold for audit trails: the server keeps the history, so nobody can quietly change the past. That is only true if nobody can tell the server what time it is.

On a default server, anyone who can write to the table can do exactly that, in two ways:

- turn on `system_versioning_insert_history` for their session and insert a version with any dates;
- move their session clock with `SET @@timestamp` and update.

Neither needs a special privilege. Only `DELETE HISTORY` has one of its own.

## See it happen

[scripts/trust_check.sh](../../scripts/trust_check.sh) makes a user with `SELECT`, `INSERT`, `UPDATE` and `DELETE` on one database, nothing else, and tries each thing. On a default server (`secure_timestamp = NO`):

| The user tries | The server says |
|---|---|
| an ordinary `UPDATE` | accepted |
| `DELETE HISTORY` | error 1142, command denied |
| `INSERT` a version dated 2015 | **accepted** |
| `UPDATE` with the session clock set to 2030 | **accepted** |

The table then holds a sugar price for 2015 that never existed, and a tea price that starts in 2030.

On a second server started with `--secure-timestamp=YES`, as root:

| Root tries | The server says |
|---|---|
| an ordinary `UPDATE` | accepted |
| `INSERT` a version dated 2015 | error 1290 |
| `UPDATE` with the session clock set to 2030 | error 1290 |

Now only the server's own clock writes history. But the same lock also refuses the import, because an import is exactly "insert a version with old dates".

## How we found it

The project imports history with `system_versioning_insert_history`. The obvious next question was who else may use that switch. Anyone who can write, it turns out. The same was true for the session clock, which I had tested for [finding 2](02-clock-set-back-loses-a-version.md).

## Why it matters

If the history is meant as proof (who changed a price, what a record said before), then any account that can write to the table can also rewrite that proof. The documentation mentions `secure_timestamp` for replication and in one line about the import switch, but nowhere says that without it the history is only as trustworthy as every account with write access.

## What works

1. **Load first.** Import the history on a server without the option.
2. **Lock after.** Restart the server with `secure_timestamp=YES`. From then on, nobody can write a past or a future, root included.
3. **Give readers a reader.** The page of this project connects with its own user that can only `SELECT` ([scripts/page_user.sh](../../scripts/page_user.sh)). Check 38 reads its grants.

## What we suggest to MariaDB

A short "Securing history" section in the documentation: by default any writer can set the time; `secure_timestamp=YES` closes that; and imported history has to be loaded before the option is switched on.

## Try it yourself

<details>
<summary>Run it (starts a second, temporary MariaDB server with the lock on)</summary>

```sh
scripts/trust_check.sh
```

It prints each case with the server's answer and cleans up after itself. The output is in [results/trust.txt](../../results/trust.txt).
</details>
