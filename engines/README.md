# Engines

## Stockfish — ground truth (required)

Any recent Stockfish (16, 17, 18) is vastly superhuman; we pin whatever the image
provides and do not chase new builds. Stockfish is a *referee*, never a role model
for how a human should think.

- Debian/Ubuntu: `apt-get install stockfish` (lands at `/usr/games/stockfish`)
- macOS: `brew install stockfish`
- Set `STOCKFISH_PATH` in `.env` if it is somewhere else.

## Maia via lc0 — human-like sparring (optional, deferred in v1)

Maia is a neural engine trained to play like a human of a given rating. A weakened
Stockfish is *not* a substitute: it plays inhuman, confusing moves. Until lc0 and the
Maia weights are installed, sparring falls back to a skill-limited Stockfish behind the
same `get_human_move` interface, and the API reports `opponent_kind: "stockfish-limited"`.

To enable Maia:

1. Install lc0 (`apt-get install lc0`, `brew install lc0`, or build from source).
2. Download Maia weights into `engines/weights/`:

   ```
   scripts/download_maia.sh          # fetches maia-1100/1500/1900 from the official release
   ```

3. Set `LC0_PATH` and `MAIA_WEIGHTS_DIR` in `.env` and restart the backend.

The backend picks the weight file whose training rating is nearest the learner's
current estimate.
