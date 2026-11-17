# MOUSE Bridge — integration workstream

Status: IN PROGRESS. No network transport or remote execution enabled.

## Scope

Integrate the independently tested Phase 1 task-snapshot prototype and the authenticated encrypted envelope prototype under `automation/mouse/`. Keep the existing `v1.py` and `v2.py` behavior unchanged until regression tests pass. Source and tests are in the companion prototype archive delivered in the ChatGPT conversation on 2026-11-17; they are **not yet committed to this branch**.

## Proposed modules

- `continuity.py`: schema validation, revision checking, atomic local task inbox.
- `secure_handoff.py`: Ed25519 sender signatures, X25519 ephemeral key agreement, HKDF-SHA256 and AES-256-GCM encrypted handoff envelopes, explicit public-key allowlist and revocation.
- `tests/test_continuity.py` and `tests/test_secure_handoff.py`: offline acceptance and rejection cases.

## Security gates before device deployment

1. Verify peer fingerprints over a separate trusted channel before approving device public keys. Do not treat a sender-supplied device ID as authentication.
2. Keep private keys in an OS-protected credential store; never commit or synchronize them in handoff snapshots.
3. Persist replay protection across restarts and handle same-revision conflicts, crashes, and concurrent writes.
4. Add strict schema, size, provenance and permissions validation; reject secrets in values, not just field names.
5. Introduce authenticated transport and explicit receipt acknowledgments; no remote execution or shell permission in this phase.
6. Run focused and full repository tests, then test across two real independently authenticated runtimes.

## Verification

Local prototype: 11 focused tests passed in an isolated Python environment on 2026-11-17. This does not establish repository CI success, cryptographic protocol audit, real device pairing, or phone-to-Codespace connectivity.

## Rollout

Phase 1: local persistence -> Phase 2: authenticated encrypted envelope -> Phase 3: network delivery and receipts -> Phase 4: phone/Codespace integration -> Phase 5: separately permissioned remote operations.
