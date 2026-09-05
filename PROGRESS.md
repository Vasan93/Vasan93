# PROGRESS

Running log of what is done, what is next, known issues, and every assumption made.

## Status

| Phase | Name | State |
|---|---|---|
| 0 | Scaffolding | **done** |
| 1 | Auth & profile | next |
| 2 | Engine service (Stockfish) | pending |
| 3 | Board & game import | pending |
| 4 | Game review + weakness seeding | pending |
| 5 | Coaching brain | pending |
| 6 | Assessment flow | pending |
| 7 | Curriculum, puzzles & SRS | pending |
| 8 | Practice sparring | pending |
| 9 | Dashboard | pending |
| 10 | Polish | pending |

## Stack decisions (Section 19.1)

| Choice | Decision |
|---|---|
| Monorepo `/backend` `/frontend` `/engines` `/infra` | Accepted |
| FastAPI + Pydantic v2 + SQLAlchemy 2.x + Alembic | Accepted |
| `python-chess` for board state, PGN, UCI | Accepted (PyPI package is named `chess`) |
| Stockfish as UCI ground truth | Accepted, pinned to whatever the image ships (v16 here) |
| Claude as the coaching brain, behind a swappable interface | Accepted |
| React + TS + Vite, react-chessboard, React Query, Zustand, Tailwind | Accepted |
| PostgreSQL | Accepted |
| Redis for engine result cache and rate limiting | Accepted, with an in-memory fallback |
| JWT + argon2 | Accepted |
| Docker Compose for local dev | Accepted, see deviation below |
| pytest + vitest | Accepted |
| Maia via lc0 | **Deferred** to a later phase, see below |

## Assumptions and deviations

1. **Python 3.11, not 3.12.** The build container ships 3.11. No 3.12-only syntax is
   used. The Docker image pins `python:3.12-slim`, so both work.
2. **Docker Compose is written but unverified here.** The Docker daemon is not running
   in this build container, so `make up` could not be executed. Postgres, Redis and the
   services were instead run natively and the acceptance criteria verified that way.
   The compose file is the supported path on a normal machine.
3. **Maia sparring is deferred (Section 9 [SWAPPABLE]).** `lc0` is not available in this
   environment and the Maia weights are a large external download. Phase 8 ships sparring
   behind the `get_human_move(fen, rating_band)` interface with a skill-limited Stockfish
   backend, and reports `opponent_kind` so the UI can be honest about it.
   **Until Maia is installed, sparring will feel less human.** `scripts/download_maia.sh`
   and `engines/README.md` cover enabling it; no application code changes are needed.
4. **`chess` 1.10.0, not the latest.** Newer releases failed to build a wheel in this
   environment. 1.10.0 has every API this project uses.
5. **Redis is optional at runtime.** `app.core.cache.Cache` falls back to an in-process
   dict so a contributor without Redis can still run the app. `/api/health` reports which
   backend is live.
6. **No `ANTHROPIC_API_KEY` in this environment.** The coaching brain is therefore built
   against its interface and exercised through a template fallback plus mocked-client
   tests. Correctness (move legality, evaluations, comprehension-check keys) never depends
   on the LLM, so this does not weaken the acceptance criteria.

## Phase 0 — Scaffolding (done)

Acceptance: everything comes online and the frontend shows a page that reads from the backend.

- Monorepo created with `/backend` `/frontend` `/engines` `/infra` `/data` `/scripts`.
- `GET /api/health` reports database, cache, Stockfish, lc0 and coaching-brain status.
- Frontend page fetches `/api/health` through the Vite proxy and renders each component.
- Verified: backend `status: ok` (postgres ok, redis live, Stockfish found), Vite dev
  server serving, proxy reaching the API, `tsc --noEmit` clean.

## Known issues

- `make up` is untested in this environment (see assumption 2).
- Sparring is not human-like until Maia is installed (see assumption 3).
