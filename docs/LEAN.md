# Standing up the Lean checker

The scoring metric needs no Lean. *Verification* does — this is the one part that requires
a real toolchain. It runs on the fleet (ren4) or in the Docker image under `docker/`.

## What has to exist

1. A Lean toolchain (`elan` + the pinned `lean-toolchain`).
2. A mathlib build (use the prebuilt cache — never compile from source; that's hours).
3. `leanprover-community/repl` — the JSON proof-checking server.
4. `GasStationManager/SafeVerify` + the bundled `leanchecker` — the anti-cheat gates.
5. The `lean-interact` Python package (`uv pip install -e ".[lean]"`).

Then `LeanInteractChecker`'s four toolchain-bound leaves get implemented:
`_run_repl`, `_print_axioms`, `_safe_verify_statement`, `_statement_of`. Everything they
feed into is already implemented and tested in `lean_checker.py`.

## ren4 disk placement (important)

ren4's internal NVMe (FIKWOT FX991) is broken — ~20 MB/s. **Models and caches live on
`/models`** (KingFast USB-C SSD, ~246 MB/s). The mathlib oleans (~5 GB) are
performance-critical, so the Lean project and the toolchain must go on `/models`, NOT the
home dir. `scripts/setup-lean-checker.sh` sets `ELAN_HOME=/models/.elan` and builds the
project under `/models/proving-ground-lean` for this reason. Putting oleans on the FIKWOT
takes `lake exe cache get` unpack from ~minutes to ~unusable.

## One-command setup (on ren4)

```bash
# from your laptop:
scp scripts/setup-lean-checker.sh ren4:/tmp/ && ssh ren4 'bash /tmp/setup-lean-checker.sh'
```

It is idempotent and confirms `/models` is mounted before writing anything large.

## Pinning (reproducibility + cache hits)

`lean/lean-toolchain` and `lean/lakefile.toml`'s mathlib `rev` must match each other and a
published cache, or `lake exe cache get` misses and falls back to a multi-hour source
build. Pin the mathlib `rev` to a specific SHA before any benchmark run, commit
`lake-manifest.json`, and freeze a corpus snapshot against that pin. The `MATHLIB_TAG`
build-arg on the Docker image serves the same purpose for containerized runs.

## Sandboxing (untrusted proofs are arbitrary code)

A submitted "proof" runs arbitrary metaprogramming; `native_decide` compiles and runs
native code. Run the checker with `--network none`, read-only mathlib, memory/cpu/pids
caps, a hard wall-clock timeout, and a non-root user — see the header of `docker/Dockerfile`.
`native_decide` is rejected twice over: as a soundness hole (the `Lean.trustCompiler`
axiom fails the allowlist) and as the primary code-execution vector.
