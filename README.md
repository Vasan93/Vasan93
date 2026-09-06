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

## Quick start — Windows, without Docker

The lightest way to run it. Three things to install, all small, and no database or cache
server: the data goes in one SQLite file and the cache lives in memory.

**1. Install the prerequisites** (skip any you already have):

| What | Where | Check it worked |
|---|---|---|
| Python 3.11+ | python.org — tick **Add python.exe to PATH** during install | `python --version` |
| Node.js 20+ | nodejs.org — the LTS installer | `node --version` |
| Stockfish | stockfishchess.org/download — get the Windows zip and extract it, for example to `C:\Vasan\Tools\stockfish` | the folder holds a `.exe` |

Close and reopen PowerShell after installing, or the new commands will not be found.

**2. Get the code and set it up:**

```powershell
cd C:\Vasan\Projects\grandmasterai
copy .env.example .env

pip install -r backend\requirements-dev.txt
cd frontend
npm install
cd ..
```

**3. Point it at Stockfish.** Open `.env` in Notepad and set the path to the `.exe` you
extracted, then save:

```
STOCKFISH_PATH=C:\Vasan\Tools\stockfish\stockfish-windows-x86-64-avx2.exe
```

The exact filename varies by download; use whatever is in that folder.

**4. Start it.** This needs two PowerShell windows, both left running.

Window one, the backend:

```powershell
cd C:\Vasan\Projects\grandmasterai\backend
python -m app.bootstrap --seed
python -m uvicorn app.main:app --reload --port 8000
```

Window two, the site:

```powershell
cd C:\Vasan\Projects\grandmasterai\frontend
npm run dev
```

Open **http://localhost:5173**.

Check http://localhost:8000/api/health if anything looks wrong. It names every part and
says which are missing, and `database` and `stockfish` are the two that must be working.

## Quick start (Docker)

Needs Docker Desktop running. Nothing else to install: Postgres, Redis and Stockfish all
come from the containers.

```bash
cp .env.example .env      # optional: add ANTHROPIC_API_KEY for real coaching
make up                   # postgres, redis, backend, frontend
```

On Windows there is no `make`, so run the command it wraps:

```powershell
copy .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

The first build takes a few minutes. When it settles, open **http://localhost:5173**.
API docs are at http://localhost:8000/docs.

To stop it: `Ctrl+C`, then `docker compose -f infra/docker-compose.yml down`. Add `-v` to
that command to drop the database and start from scratch.

Compose supplies PostgreSQL and Redis and overrides the database and cache settings in
`.env`, so the same `.env` file is correct whichever way you start the app.

## Quick start (macOS or Linux, without Docker)

```bash
cp .env.example .env
pip install -r backend/requirements-dev.txt
cd frontend && npm install && cd ..

make seed                 # create the SQLite database and load the puzzle bank
make dev-backend          # http://localhost:8000
make dev-frontend         # http://localhost:5173   (a second terminal)
```

Stockfish comes from `brew install stockfish` or `apt install stockfish`.

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

## First run

The app works immediately with no API key. Sign up, take the ten-position assessment, then
paste a PGN on the Games page and press **Review this game** to see the engine find the
mistakes and the coach name the patterns behind them. If you have no game handy, the Play
page gives you one against the bot in a couple of minutes.

`JWT_SECRET` can stay blank locally: the server generates a random key at startup, which
signs everyone out when it restarts but never uses a key published in this repository.
Set a real one with `openssl rand -hex 32` before deploying anywhere.

## Coaching without an API key

If `ANTHROPIC_API_KEY` is unset the app still runs end to end. Coaching text falls back
to engine-grounded templates: correctness stays objective, only the warmth is missing,
and the interface says so rather than passing it off as coaching. `/api/health` reports
which mode is active.

## Human-like sparring

Maia is a neural engine trained to play like a human of a given rating. Without it,
sparring falls back to a strength-limited Stockfish, which plays weaker but less like a
person. `engines/README.md` covers enabling Maia; no application code changes.
