# Tablekeeper — stage plan and verification checklist

**For humans.** This file is how we judge, after a run, whether the band's output meets
the specification beyond the shipped checks. It is *not* given to the band: the dispatch
contains only the official spec paths, and the coordinator writes its own requirements
checklist. (Pasting our plan into the dispatch would make it our design, not the band's.)
Track vocabulary is fine here; it must never appear in `mandates/`.

Shipped share of graded checks: stage 1 **83%**, stage 2 **41%**, stage 3 **11%**, stage 4
**21%**. Stages 3–4 are graded almost entirely on tests we cannot see.

## Cross-cutting design constraints (any sound implementation must satisfy)

- Single container, `PORT` env (default 8080), healthy < 60 s, 2 vCPU / 2 GiB, ≤ 50 in-flight
  requests, 5 s per request (10 s reset/import/export), **no runtime network** — fonts, JS,
  CSS for stage 2 are served from the image.
- All writes serialisable: one lock / one transaction around check-and-write of occupancy,
  idempotency records and revisions. No 5xx ever, including under concurrency.
- Error body `{"error":{"code","message"}}` on every 4xx/5xx; 400 only for unparseable body
  or wrong JSON type; 422 for range/format; precedence rules in stage-1 §5.
- Time: resolve local wall time with real IANA rules (DST gap → `invalid_local_time`; fall-back
  → first occurrence); durations in absolute minutes; RFC 3339 with offset in responses.
- Idempotency: per user; replay = same method + path + JSON-equal body → 200 with original
  body; different body → 409 even if the new body is invalid; key reusable after a 4xx;
  concurrent first uses → exactly one 201.
- Export/import: lossless (users, password hashes, tokens, reservations, idempotency
  receipts, revisions, histories, series, plans, counters); import is atomic replacement; a
  later stage must import every earlier stage's export.

## Stage 1 — JSON API (gate 3 lives here)

Build: health, reset/seed, auth (signup/login, hashed passwords, bearer tokens), restaurants
list/detail, availability, create/list/get/cancel/patch reservation, export/import,
atomic multi-reservation moves.

Probe beyond shipped checks:
- slot grid from `opens`; last slot ends exactly at `closes`; closed weekday → `slots: []`
- spring-forward local time absent from availability and 422 on create; fall-back slot appears
  once; 90-min booking at 01:30 on fall-back night ends "02:00" local
- half-open overlap (19:00 + 90 min vs 20:30 is free)
- `party_size` string/bool/0 → 422; `starts_at_local` with seconds/offset → 422; query ints
  like `4.0`, `+4`, `1e9` → 422; Idempotency-Key 256 chars → 422, empty → 400
- cancel twice → 200; cancel/patch inside cutoff (against current start) → 409 `cutoff_passed`
- patch to own current slot does not self-conflict; failed patch leaves occupancy unchanged
- reference 6–12 `[A-Z0-9]`, stable across patch; other user's reference → 404 everywhere
- moves: 1..8 distinct refs, cross-restaurant → 422, swap of two bookings' tables succeeds
  atomically, any failure changes nothing incl. idempotency key; replay after cancel → 200
- 50 concurrent creates for one table/slot → exactly one 201

## Stage 2 — browser product + combined tables

Build: `/`, `/signup`, `/login`, `/lookup` HTML; every `data-testid` in the spec; combinable
pairs in model, availability `available_options`, `table_ids` on create/patch/moves/responses.

Probe beyond shipped checks:
- out-of-order searches (late response A must not overwrite B) — request sequencing token
- 409 on submit → `booking-error`, availability refresh, form inputs preserved
- lost response → `booking-uncertain`, retry with **same key and body**, original reference
- resubmitting an unchanged form returns the same reference; changing a field = new key
- signed-in browser survives stage-1 export → stage-2 import (tokens preserved)
- pairs: not transitive, unordered input, `table_id` only when single, both fields → 422,
  3 tables → `combination_not_allowed`, capacity = sum
- 375 px viewport without horizontal scroll; visible labels, focus rings, distinct states
  (App score is 25%: coherent hospitality look, not a test harness)

## Stage 3 — explanations, history, policies, recurring series

Build: `explain=true` (only literal `true`), history with `seq`, policies (managers only,
versioned, effective-dated, accepted-terms snapshot per booking), `revision` +
`expected_revision`, `/decision`, `POST /series`, `GET /series/{id}`, combined-table history,
moves under policies.

Probe beyond shipped checks:
- policy selection by booking's local start date; same-date tie → highest version; past
  effective dates never rewrite accepted bookings
- no-op PATCH: 200, no history entry, no revision bump; cancel bumps revision once
- `expected_revision` stale → 409 before cutoff; concurrent amendments at one revision → one wins
- series: occurrence i at +7·i·interval days same local clock time; DST gap anywhere →
  whole adoption fails `invalid_local_time` with nothing persisted; occurrences select their
  own date's policy; individual PATCH marks `exception` permanently
- restaurant revision counter (needed in stage 4) increments exactly as specified
- imports from stage-1 and stage-2 exports, then adopt a series from an imported booking

## Stage 4 — closure replanning, series amendments

Build: `POST /restaurants/{id}/replans` (preview, deterministic optimum), `/apply`
(atomic, stale/applied rules), closures affecting availability/explain/creates,
`POST /series/{id}/amend`.

Probe beyond shipped checks:
- exhaustive search over options per considered booking (≤ 6 bookings, ≤ 10 options each)
  with the 3-level lexicographic objective; ties by option-rank vector in reference order
- cutoff never blocks a repair; accepted terms used for capacity
- any intervening restaurant revision → 409 `stale_plan`; applied under other key →
  `plan_already_applied`; replay → original 200
- closures exclude singles and pairs containing the table; `no_overlap` false in explain
- series amend: skips cancelled and exception occurrences, cutoff + policy per occurrence,
  all-or-nothing, no exception marking, revisions bump once if anything changed

## How to validate each stage after the band finishes

```bash
cd ~/band-work/kickoff
~/band-work/.venv/bin/python -m harness run --track tablekeeper --repo ~/band-work/<run> --stage N --mode isolated --out ~/band-work/checks/<run>-final-sN
```

Want `claimed stage: N`. Then walk this file's probe list for that stage by hand against the
running container and record gaps in `docs/teammate_handoff.md`. Gaps are fixed only by the
band (a new dispatched run), never by a human commit.
