# PROGRESS

Running log of what is done, what is next, known issues, and every assumption made.

## Status

| Phase | Name | State |
|---|---|---|
| 0 | Scaffolding | **done** |
| 1 | Auth & profile | **done** |
| 2 | Engine service (Stockfish) | **done** |
| 3 | Board & game import | **done** |
| 4 | Game review + weakness seeding | **done** |
| 5 | Coaching brain | **done** |
| 7 | Curriculum, puzzles & SRS | **done** |
| 6 | Assessment flow | next |
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
6. **Live username import cannot be exercised here.** This container's network policy
   blocks `lichess.org` and `api.chess.com` (only package registries are reachable), so
   `POST /games/import/username` is verified against a mocked HTTP transport that
   exercises the real parsing, pagination and error paths. PGN upload, the primary
   import path, is verified live.
7. **No `ANTHROPIC_API_KEY` in this environment.** The coaching brain is therefore built
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

## Phase 1 — Auth & profile (done)

Acceptance: a user can register, log in, set language, and stay logged in.

- `POST /api/auth/signup`, `POST /api/auth/login`, `GET|PATCH /api/auth/me`,
  `GET /api/auth/languages` (21 languages, including Tamil, Hindi, Telugu, Kannada,
  Malayalam, Bengali and Marathi).
- argon2 password hashing, JWT bearer tokens, rate limits on signup and login,
  identical error text for unknown email and wrong password.
- Startup warns loudly if `JWT_SECRET` is short or still the default.
- Full Section 8 schema declared up front and captured in the first Alembic migration,
  so foreign keys stay consistent as later phases fill the tables.
- Frontend: signup/login page, app shell, profile page. Token persists in
  `localStorage`; a reload restores the session through `GET /auth/me`.
- Verified: 10 backend tests pass; browser run signs up in Tamil, switches to a
  profile page, and survives a reload still authenticated.

## Phase 2 — Engine service (done)

Acceptance: given a FEN and a move, the service returns the best move, an evaluation
and a correct classification, verified by tests on known positions.

- `app/engines/base.py` holds the interface: `AnalysisEngine.analyze` / `.classify_move`
  and `SparringEngine.get_human_move`. Nothing above this package touches a binary.
- `app/engines/stockfish.py` wraps Stockfish over UCI with a bounded depth-and-time
  limit, a Redis-backed result cache, automatic restart on engine death, and strict FEN
  validation. An illegal position crashes the Stockfish process rather than erroring, so
  the validation guard is load-bearing, not decorative.
- Move labels combine centipawn loss with win-probability loss and take the milder of
  the two. The same 200cp drop is a blunder in an equal position and only an inaccuracy
  when already winning by a queen, which is the fair judgement.
- A forced mate overrides that softening in both directions: missing mate while winning
  is still flagged, because win probability barely moves and a coach must not stay quiet.
- `app/engines/motifs.py` names the mistake: missed mate, allowed mate, hung piece,
  missed capture, missed fork, missed pin, missed skewer, missed discovered attack,
  ignored threat, plus opening-principle and endgame patterns. Detection can only emit
  real taxonomy keys, enforced by a test.
- `app/engines/boardlib.py` provides the primitives, including a recursive static
  exchange evaluator played on a real board so pins, x-rays and promotions are handled.
- `app/weakness/taxonomy.py` defines the 24-key taxonomy from Section 11, each key
  carrying a teaching topic and the Lichess puzzle themes that train it.
- Endpoints: `POST /api/engine/analyze`, `POST /api/engine/classify`,
  `GET /api/engine/sparring-info`, all authenticated and rate limited.
- Verified: 40 backend tests pass. Live checks show the start position evaluated at
  +46 for e4, `Nd4` classified as a mistake with motif `hung_piece`, an illegal FEN
  rejected with 400, and unauthenticated access rejected with 401.

## Phase 3 — Board & game import (done)

Acceptance: a user can import a game and step through it on the board.

- `app/services/pgn.py` parses PGN into per-ply records with the position before each
  move, handling comments, variations and NAGs.
- **Truncated PGNs are rejected rather than silently shortened.** `python-chess` drops
  move tokens it cannot parse and reports no error, so a corrupted file would import as
  a shorter game that was never played and be coached as fact. The parser counts the
  move tokens written in the movetext and refuses the import when that disagrees with
  what parsed. Splitting a multi-game file slices the original characters instead of
  re-serialising, because re-serialising would erase the evidence.
- `app/services/game_sources.py` fetches public games from Lichess and Chess.com, with
  readable errors for unknown players and rate limiting.
- Endpoints: `POST /api/games/import/pgn` (single or multi-game),
  `POST /api/games/import/username`, `GET /api/games`, `GET /api/games/{id}`,
  `DELETE /api/games/{id}`. Games are private to their owner, enforced by a test.
- Frontend: import form, game list, and a board viewer with a synced move list and
  keyboard playback (arrow keys, Home, End).
- **Fixed a real cache bug found by the tests.** The in-memory fallback ignored TTL, so
  a deployment without Redis would keep rate-limit counters for ever and lock users out.
  The fallback now expires keys with the same semantics as Redis.
- Verified: 67 backend tests pass. A browser run signs up, imports Legall's Mate, opens
  it, and steps to the final position with the move list highlighting `Nd5#`.

## Phase 4 — Game review & weakness seeding (done)

Acceptance: importing a game populates a visible list of weaknesses with confidence scores.

- `app/services/review.py` labels every move the learner played, stores the verdict, and
  scores game accuracy from win-probability loss using the Lichess curve.
- `app/services/jobs.py` runs reviews on a worker pool and publishes progress through the
  shared cache, so the UI can show a progress bar. The `submit`/`status` interface is what
  callers depend on, so swapping in RQ or Celery later is a change inside that module.
- `app/weakness/model.py` is pure logic with no engine or LLM inside. Confidence saturates
  rather than growing without bound, so one blunder is noise and the same motif three
  times is a pattern. Successes pull confidence back down; a weakness only retires after
  spaced successes, and a failure reopens it.
- `app/weakness/service.py` persists the profile, keeping the raw evidence weight
  alongside the derived confidence so the curve can be recomputed without drift.
- Endpoints: `POST /api/games/{id}/review`, `GET /api/games/{id}/review`,
  `GET /api/weaknesses`.
- Frontend: review progress bar, move list annotated with `?!`, `?` and `??`, a green
  arrow showing the engine's preferred move, plain-language explanation of the swing, and
  a weakness page grouped by category with confidence shown as a bar.
- **Fixed a real hang.** `python-chess` runs each engine's event loop on a non-daemon
  thread, and CPython joins those *before* running `atexit` handlers, so an
  `atexit`-registered close never fires and any command-line entry point that touched the
  engine would hang for ever. `app/engines/lifecycle.py` registers cleanup through
  `threading._register_atexit`, the same hook `concurrent.futures` uses.
- Verified: 82 backend tests pass. A browser run imports a blunder-filled game, reviews
  it to 70.9% accuracy, shows `14. Nd2` as a blunder with the arrow to `Qxc5`, and lists
  nine weaknesses led by hanging pieces at 80% confidence.

## Phase 5 — Coaching brain (done)

Acceptance: clicking a mistake yields a warm, correct explanation in the learner's
language, tied to a weakness.

- `app/coaching/prompts/v1.py` holds every template, versioned together so a change in
  coaching voice is a reviewable diff. The persona names the learner's language and
  forbids switching, forbids inventing evaluations, and carries their goal.
- `app/coaching/brain.py` defines the `CoachingBrain` interface with two implementations.
  `ClaudeBrain` calls Claude with adaptive thinking, low effort for prose, a JSON schema
  for lessons, and server-side refusal fallbacks so a decline never leaves a learner with
  nothing. `TemplateBrain` produces engine-grounded text without any model.
- **The brain never decides chess facts.** `app/coaching/validation.py` checks every
  position it invents for legality, drops illegal examples, and re-derives every
  comprehension-check answer from the engine. When the model's key disagrees with
  Stockfish, the engine wins and the correction is recorded. Student answers are graded
  by the engine too, with a 50cp margin so a second good move is not marked wrong.
- Without an API key, lessons are built from the learner's *own* mistake positions rather
  than invented ones, and a lesson with no evidence behind it is refused rather than
  fabricated.
- Every prompt and response is written to `coaching_logs` for quality review.
- The fallback is honest: responses carry the language actually used alongside the
  language the learner asked for, and the UI says which.
- Endpoints: `POST /api/coach/explain`, `POST|GET /api/coach/lessons`,
  `GET /api/coach/lessons/{id}`, `POST /api/coach/lessons/{id}/check`,
  `POST /api/coach/chat`. The answer key never leaves the server before the student tries.
- Verified: 104 backend tests pass, including the full Claude request path against a fake
  client (request shape, structured lessons, refusal handling, malformed JSON). A browser
  run explains a blunder in context and completes a lesson whose check is graded against
  the engine.

## Phase 7 — Curriculum, puzzles & SRS (done)

**Built before Phase 6.** The adaptive assessment serves calibrated puzzles, so it needs
the puzzle bank that this phase creates. Doing them in the brief's order would have meant
building the assessment against a bank that did not exist yet.

Acceptance: the app serves the right next puzzle for the learner's top due weakness, and
progression is tracked.

- `data/puzzles.seed.json` holds 28 curated puzzles across 15 taxonomy keys, every one
  verified against Stockfish by `scripts/build_seed_puzzles.py`. Verification is in two
  modes, because a single rule was wrong for half the bank:
  - **Tactical** puzzles must have one answer: the stated move must be the engine's, and
    clearly better than the runner-up. On mating positions the comparison is by *mate
    distance*, since folded mate scores put mate-in-1 and mate-in-3 two centipawns apart.
  - **Concept** puzzles teach judgement, where several moves are reasonable. The stated
    move only has to be within tolerance of the best, and grading uses the same tolerance
    so a second good move is not marked wrong.
  Eight positions were dropped outright because the engine disagreed with the intended
  point. A puzzle that cannot be graded fairly is not shipped.
- `scripts/import_lichess_puzzles.py` imports a balanced sample of the open Lichess
  database (CC0), capped per taxonomy key and per rating band so every level stays
  calibrated.
- `app/curriculum/srs.py` is an SM-2 scheduler, pure and tested. Intervals grow
  1 → 3 → 8 → 23 days; a miss resets the interval and costs a success; solving quickly
  raises ease more than grinding it out.
- `app/curriculum/service.py` picks the highest-confidence active weakness whose card is
  due, then a puzzle near the learner's rating (150 below to 250 above, targeting slightly
  above for stretch), skipping anything already solved.
- **Retirement has one authority.** The weakness model and the SRS card were both
  deciding it, and disagreeing. Counting successes cannot tell crammed practice from
  spaced practice, so `status_for` no longer returns "retired" at all: the card decides,
  and a lapse reopens the weakness.
- Endpoints: `GET /api/puzzles/next`, `POST /api/puzzles/{id}/attempt`, `GET /api/curriculum`.
- Frontend: a training page with a playable board (drag or click-to-move), coach feedback
  on every attempt, and the due list.
- **Fixed a second shutdown hang.** Cleanup handlers were consumed when they ran, so an
  engine restarted after shutdown had no cleanup registered and its non-daemon thread hung
  the interpreter. The registry is no longer cleared.
- Verified: 124 backend tests pass and the suite exits cleanly. A browser run reviews a
  game, is served a puzzle matching its top weakness, gets the wrong-answer branch right,
  and moves on to the next weakness.

## Known issues

- `make up` is untested in this environment (see assumption 2).
- Sparring is not human-like until Maia is installed (see assumption 3).
