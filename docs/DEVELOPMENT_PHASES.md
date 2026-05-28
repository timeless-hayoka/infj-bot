# PHI // DRIFT — Development Phases

*Saved 2026-05-28*

---

## Phase 1 — Finish Unification (Phases 3–5)

Do this first. Until DRIFT and hive_mind are fully consolidated into infj_bot, any tests you write against fragmented modules will need to be rewritten. Stabilize the structure before building on top of it.

## Phase 2 — Test Coverage

Once the unified architecture is stable, systematically cover the cognitive modules that currently have zero tests. Starting here before unification means rework.

## Phase 3 — GPU Acceleration

With a clean, tested codebase, add the GPU inference path for local models. This is a contained technical addition that doesn't need to block the others.

## Phase 4 — Observer / Dashboard Polish

Can run in parallel with Phase 3. The cognitive state is the interesting thing to observe — better to do this once the unified architecture is settled so the dashboard reflects the real structure.

## Phase 5 — Outward-Facing Positioning

A product narrative, landing page, or research-facing one-pager. Do this last so it reflects the finished system — but it can be drafted in parallel once you know what's in scope.

---

## Order rationale

| Step | Why it comes here |
|------|-------------------|
| Unification first | Fragmented modules mean test rework later |
| Tests second | You can't trust what you can't measure |
| GPU third | Contained addition, clean codebase makes it easy |
| Dashboard fourth | Reflects real unified architecture |
| Positioning last | Describes the finished thing |
