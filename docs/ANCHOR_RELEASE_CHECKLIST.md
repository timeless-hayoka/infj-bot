# ANCHOR Release Checklist

Status: release-candidate, not fully finished.

## Must Pass Before Full Release

- Fresh install works on a clean machine.
- `bootstrap_anchor.sh` completes without manual repair.
- The desktop launcher opens the correct ANCHOR UI.
- Remote mode can bind to `0.0.0.0` with `ANCHOR_WEB_HOST` and advertise a real `ANCHOR_PUBLIC_URL`.
- The dashboard loads the core panels:
  - System health
  - Release identity
  - Evidence metrics
  - Knowledge vault
  - Contribution tracking
- Optional panels degrade cleanly with clear `READY / OPTIONAL / ERROR / LOADING` states.
- `GET /api/trinity/vault` returns sane counts and freshness metadata.
- `GET /api/trinity/contributions` returns safe values or an explicit fallback source.
- Trinity smoke tests pass.
- Release banner and changelog entry are present.
- Required changesets exist for package-affecting changes.
- Startup warnings do not block normal use.

## Current Assessment

- Release-candidate: yes
- Fully finished: no
- Main remaining work: packaging, fresh-install validation, and release hygiene
## Service Profiles

- Local mode: `systemctl --user enable --now anchor-web@local.service`
- Server mode: `systemctl --user enable --now anchor-web@server.service`
- Switch cleanly by stopping the current instance, enabling the target instance, and updating `~/.config/anchor/anchor-web-*.env` as needed.


## Suggested Release Gate

Do not call the project fully released until a fresh install can:

1. Install cleanly.
2. Launch ANCHOR.
3. Load the dashboard.
4. Show healthy core panels.
5. Survive optional-panel failures without breaking startup.

