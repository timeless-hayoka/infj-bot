# Trinity hunt scripts (in-repo)

Primary entry point for proof-gated bug hunts:

```bash
cd /path/to/infj_bot
PYTHONPATH=. python hunts/trinity_hunt.py --help
```

Or via the drift launcher:

```bash
./scripts/drift trinity demo   # smoke caseflow
```

Hunt output feeds the ANCHOR pipeline (`caseflow` → council → ledger). Logs land in `hunts/logs/` when using the built-in transcript helper.

**Requires:** Foundry (`forge`), optional scanner tools (Slither, etc.) depending on flags.
