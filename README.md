# GrandmasterAI

A standalone AI chess coach. It assesses a player, teaches the concepts that player
specifically needs, diagnoses recurring weaknesses, assigns targeted puzzles, tests
understanding during lessons, tracks growth over time, speaks the learner's language,
and talks with genuine warmth.

## The core principle

**A chess engine is a brilliant player but a terrible teacher.** Stockfish gives a best
move and a number. It never explains *why* in human terms, never notices a learner's
recurring *patterns* of error, and has no warmth.

So the layers are strictly separated:

| Layer | Job | Rule |
|---|---|---|
| Engine (Stockfish) | Ground truth: best move, evaluation, mistake detection | Never teaches |
| Sparring (Maia via lc0) | A human-*feeling* opponent at the learner's level | Never a weakened Stockfish |
| Coaching brain (Claude) | Explanation, personalization, language, warmth | Never invents an evaluation |
| Weakness model | Aggregates mistakes into patterns, decides what to teach | Pure logic, no LLM |

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

make dev-backend          # http://localhost:8000
make dev-frontend         # http://localhost:5173
```

## Repository layout

```
backend/     FastAPI service (app/engines, app/coaching, app/weakness, app/curriculum)
frontend/    React + TypeScript + Vite
engines/     Engine binaries and Maia weights (see engines/README.md)
infra/       Docker Compose and Dockerfiles
data/        Seed data (puzzle bank)
scripts/     Operational scripts
```

## Tests

```bash
make test           # backend pytest + frontend vitest
```

## Coaching without an API key

If `ANTHROPIC_API_KEY` is unset the app still runs end to end. Coaching text falls back
to engine-grounded templates: correctness stays objective, only the warmth is missing.
`/api/health` reports which mode is active.
