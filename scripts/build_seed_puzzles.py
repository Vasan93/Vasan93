"""Build and verify the bundled seed puzzle bank.

Two kinds of puzzle, verified differently:

  * **Tactical** puzzles have one right answer. The stated move must be the engine's
    choice and clearly better than the runner-up, otherwise grading is unfair.
  * **Concept** puzzles teach judgement (develop, castle, activate the king). Positions
    like these usually have several reasonable moves, so the stated move only has to be
    within tolerance of the best, and grading uses that same tolerance.

A puzzle that fails its check is dropped rather than shipped.
"""
import json, sys
import chess
from app.engines.stockfish import StockfishEngine

OUT = "/home/user/Vasan93/data/puzzles.seed.json"
STRICT_MARGIN = 150   # tactics: the runner-up must be clearly worse
CONCEPT_TOLERANCE = 70  # concepts: any move this close to best is accepted

# (id, fen, solution, taxonomy_key, themes, rating, kind)
RAW = [
    # ---------------------------------------------------------------- tactical
    ("gm-br1", "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra8#", "back_rank", "backRankMate mateIn1", 600, "tactical"),
    ("gm-br2", "3r2k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "Rxd8#", "back_rank", "backRankMate", 800, "tactical"),
    ("gm-m1a", "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "Qxf7#", "missed_mate", "mateIn1 attackingF2F7", 500, "tactical"),
    ("gm-m1b", "6rk/6pp/8/6N1/8/8/8/6K1 w - - 0 1", "Nf7#", "missed_mate", "mateIn1 smotheredMate", 750, "tactical"),
    ("gm-m1c", "2k5/8/2K5/8/8/8/8/4R3 w - - 0 1", "Re8#", "basic_checkmates", "mateIn1 endgame", 550, "tactical"),
    ("gm-m1d", "7k/8/6K1/8/8/8/8/R7 w - - 0 1", "Ra8#", "basic_checkmates", "mateIn1 rookEndgame endgame", 500, "tactical"),
    ("gm-m1e", "6k1/5ppp/8/8/8/8/5PPP/3Q2K1 w - - 0 1", "Qd8#", "missed_mate", "mateIn1 backRankMate", 600, "tactical"),
    ("gm-fk1", "8/2q1k3/8/8/8/4N3/8/6K1 w - - 0 1", "Nd5+", "missed_forks", "fork advantage", 700, "tactical"),
    ("gm-fk2", "2q3k1/8/8/3N4/8/8/8/6K1 w - - 0 1", "Ne7+", "missed_forks", "fork", 750, "tactical"),
    ("gm-pn1", "3k4/3q4/8/8/8/8/8/R3K3 w - - 0 1", "Rd1", "missed_pins_skewers", "pin", 800, "tactical"),
    ("gm-sk2", "8/8/8/8/q3k3/6K1/8/7R w - - 0 1", "Rh4+", "missed_pins_skewers", "skewer", 900, "tactical"),
    ("gm-hp1", "4k3/8/8/8/2n5/8/8/2R1K3 w - - 0 1", "Rxc4", "missed_captures", "hangingPiece", 500, "tactical"),
    ("gm-hp3", "4k3/8/8/3b4/8/8/8/3RK3 w - - 0 1", "Rxd5", "missed_captures", "hangingPiece", 500, "tactical"),
    ("gm-hp5", "7k/8/8/8/8/8/6q1/K5R1 w - - 0 1", "Rxg2", "missed_captures", "hangingPiece", 550, "tactical"),
    ("gm-hp6", "3r3k/8/8/8/8/8/8/3RK3 w - - 0 1", "Rxd8+", "back_rank", "hangingPiece backRankMate", 650, "tactical"),
    ("gm-df2", "r5k1/5ppp/8/8/8/8/5PPP/R5K1 b - - 0 1", "Rxa1#", "threat_checking", "backRankMate mateIn1", 700, "tactical"),
    ("gm-da1", "3k4/8/8/3N4/2q5/8/8/3RK3 w - - 0 1", "Nb6+", "missed_discovered_attacks", "discoveredAttack fork", 1050, "concept"),
    # ----------------------------------------------------------------- concept
    ("gm-op2", "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "Nf3", "opening_principles", "opening", 600, "concept"),
    ("gm-op3", "rnb1kbnr/pppp1ppp/8/4p3/4P2q/8/PPPP1PPP/RNBQKBNR w KQkq - 2 3", "Nc3", "opening_principles", "opening", 700, "concept"),
    ("gm-op4", "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", "Nf6", "piece_development", "opening", 800, "concept"),
    ("gm-ks1", "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 5", "O-O", "king_safety", "opening castling", 800, "concept"),
    ("gm-kp1", "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1", "Kd6", "opposition", "pawnEndgame endgame opposition", 1100, "concept"),
    ("gm-kp2", "8/4k3/8/4K3/8/8/4P3/8 w - - 0 1", "e3", "opposition", "pawnEndgame endgame", 1250, "concept"),
    ("gm-pr1", "8/1P6/8/8/8/8/8/k6K w - - 0 1", "b8=Q", "pawn_promotion", "promotion advancedPawn endgame", 500, "concept"),
    ("gm-pr2", "8/8/8/8/8/8/1p2k3/1K6 b - - 0 1", "Kd3", "pawn_promotion", "pawnEndgame promotion endgame", 1150, "concept"),
    ("gm-ro1", "8/8/8/8/8/2k5/8/K3R3 w - - 0 1", "Rd1", "rook_endgames", "rookEndgame endgame", 1000, "concept"),
    ("gm-ro2", "5k2/pp3ppp/8/8/8/8/PP3PPP/2R2K2 w - - 0 1", "Rc7", "rook_endgames", "rookEndgame endgame", 950, "concept"),
    ("gm-pa1", "r4rk1/pp3ppp/8/8/8/8/PP3PPP/2R2RK1 w - - 0 1", "Rc7", "piece_activity", "quietMove", 1100, "concept"),
]


def main() -> int:
    engine = StockfishEngine(depth=18, seconds=1.0, multipv=3)
    if not engine.available:
        print("Stockfish required")
        return 1

    out, rejected = [], []
    for pid, fen, solution, key, themes, rating, kind in RAW:
        board = chess.Board(fen)
        if not board.is_valid() or board.is_game_over():
            rejected.append((pid, "unusable position"))
            continue
        try:
            move = board.parse_san(solution)
        except ValueError:
            rejected.append((pid, f"illegal move {solution}"))
            continue

        analysis = engine.analyze(fen, depth=18, multipv=3)
        best = analysis.best
        runner_up = analysis.top_moves[1].score_cp if len(analysis.top_moves) > 1 else best.score_cp - 9999
        margin = best.score_cp - runner_up

        if kind == "tactical":
            if best.move_san != solution:
                rejected.append((pid, f"engine plays {best.move_san}, not {solution}"))
                continue

            if best.mate_in and best.mate_in > 0:
                # Folded mate scores put mate-in-1 and mate-in-3 two centipawns apart, so
                # compare mate distance instead: the answer must be the fastest mate.
                second = analysis.top_moves[1] if len(analysis.top_moves) > 1 else None
                if second is not None and second.mate_in and 0 < second.mate_in <= best.mate_in:
                    rejected.append((pid, f"not unique: {second.move_san} also mates in {second.mate_in}"))
                    continue
            elif margin < STRICT_MARGIN:
                rejected.append((pid, f"not unique: {analysis.top_moves[1].move_san} is only {margin}cp worse"))
                continue
            tolerance = 30
        else:
            verdict = engine.classify_move(fen, solution, depth=18)
            loss = verdict.cp_loss
            if loss > CONCEPT_TOLERANCE:
                rejected.append((pid, f"{solution} loses {loss}cp; engine plays {best.move_san}"))
                continue
            tolerance = CONCEPT_TOLERANCE

        out.append({
            "id": pid,
            "fen": fen,
            "solution_moves": move.uci(),
            "solution_san": board.san(move),
            "themes": themes,
            "taxonomy_keys": key,
            "rating": rating,
            "kind": kind,
            "tolerance_cp": tolerance,
            "popularity": 0,
            "source": "curated",
        })

    print(f"accepted {len(out)} / {len(RAW)}")
    for pid, why in rejected:
        print(f"  REJECT {pid}: {why}")
    with open(OUT, "w") as handle:
        json.dump(out, handle, indent=1)
    print("wrote", OUT)
    return 0


sys.exit(main())
