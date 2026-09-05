# GrandmasterAI

A standalone AI chess coach. It assesses a player, teaches the concepts that player
specifically needs, diagnoses recurring weaknesses, assigns targeted puzzles, tests
understanding during lessons, tracks growth over time, speaks the learner's language,
and talks with genuine warmth.

## The core principle

**A chess engine is a brilliant player but a terrible teacher.** Stockfish gives a best
move and a number. It never explains *why* in human terms, never notices a learner's
recurring *patterns* of error, and has no warmth.

So the layers are strictly separated, and the separation is enforced in code:

| Layer | Job | Rule |
|---|---|---|
| Engine (Stockfish) | Ground truth: best move, evaluation, mistake detection | Never teaches |
| Sparring (Maia via lc0) | A human-*feeling* opponent at the learner's level | Never a weakened Stockfish |
| Coaching brain (Claude) | Explanation, personalisation, language, warmth | Never invents an evaluation |
| Weakness model | Aggregates mistakes into patterns, decides what to teach | Pure logic, no LLM |

Every position the coaching brain invents is checked for legality, and every
comprehension-check answer is re-derived from the engine. When the model's answer key
disagrees with Stockfish, the engine wins.

## What a learner does

1. **Assessment.** Ten adaptive positions across tactics, endgames, openings and
   strategy produce a starting rating and a first weakness profile.
2. **Import games.** Paste a PGN or pull public games from Lichess or Chess.com. A
   background review labels every move and turns mistakes into *patterns*, not one-offs.
3. **Understand.** Click any mistake and the coach explains it in the learner's language,
   tied to the pattern behind it.
4. **Learn.** Lessons target one weakness, built where possible from the learner's own
   positions, and end in a comprehension check graded by the engine.
5. **Train.** Spaced repetition serves the next puzzle for the top due weakness, near the
   learner's rating. A weakness retires only after repeated success at growing intervals.
6. **Play.** A practice game at the learner's level, reviewed and fed back into the
   profile.
7. **Track.** Rating trajectory, per-weakness progress, streaks and accuracy.

## Quick start (Docker)

```bash
cp .env.example .env      # add ANTHROPIC_API_KEY for real coaching
make up                   # postgres, redis, backend, frontend
```

Frontend at http://localhost:5173, API docs at http://localhost:8000/docs.

## Quick start (native, no Docker)

Requires PostgreSQL, Redis and Stockfish on the host.

```bash
cp .env.example .env
pip install -r backend/requirements-dev.txt
cd frontend && npm install && cd ..

make seed                 # create tables and load the puzzle bank
make dev-backend          # http://localhost:8000
make dev-frontend         # http://localhost:5173
```

## Repository layout

```
backend/     FastAPI service
  app/engines/     Stockfish ground truth, motif detection, sparring
  app/coaching/    Versioned prompts, the brain interface, guardrails
  app/weakness/    Taxonomy and the pure weakness model
  app/curriculum/  Puzzle bank and the SM-2 scheduler
  app/assessment/  Adaptive rating estimation
  app/practice/    Practice games
frontend/    React + TypeScript + Vite
engines/     Engine binaries and Maia weights (see engines/README.md)
infra/       Docker Compose and Dockerfiles
data/        The verified seed puzzle bank
scripts/     Puzzle import, seed building, Maia download
```

## Tests

```bash
make test                 # backend pytest + frontend vitest
cd backend && pytest -m "not slow"    # skip the engine-heavy end-to-end tests
```

## The puzzle bank

`data/puzzles.seed.json` ships 28 curated puzzles across 15 taxonomy keys, each verified
against Stockfish by `scripts/build_seed_puzzles.py`. Tactical puzzles must have one
answer clearly better than the runner-up; concept puzzles accept any move within
tolerance, because positional ideas rarely have a single right move.

For a real deployment, import a balanced sample of the open Lichess puzzle database:

```bash
curl -O https://database.lichess.org/lichess_db_puzzle.csv.zst
zstd -d lichess_db_puzzle.csv.zst
python scripts/import_lichess_puzzles.py lichess_db_puzzle.csv
```

## Coaching without an API key

If `ANTHROPIC_API_KEY` is unset the app still runs end to end. Coaching text falls back
to engine-grounded templates: correctness stays objective, only the warmth is missing,
and the interface says so rather than passing it off as coaching. `/api/health` reports
which mode is active.

## Human-like sparring

Maia is a neural engine trained to play like a human of a given rating. Without it,
sparring falls back to a strength-limited Stockfish, which plays weaker but less like a
person. `engines/README.md` covers enabling Maia; no application code changes.
