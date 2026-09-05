"""Phase 2 acceptance: given a FEN and a move, the engine service returns the best move,
an evaluation, and a correct classification -- verified on positions with known answers.
"""
from __future__ import annotations

import chess
import pytest

from app.engines import boardlib as bl
from app.engines import motifs
from app.engines.base import at_least, classify_loss, win_probability
from app.engines.sparring import SparringService, nearest_band
from app.engines.stockfish import StockfishEngine

pytestmark = pytest.mark.usefixtures("_schema")


@pytest.fixture(scope="module")
def engine() -> StockfishEngine:
    eng = StockfishEngine(depth=14, seconds=0.3)
    if not eng.available:
        pytest.skip("Stockfish binary not installed; set STOCKFISH_PATH")
    yield eng
    eng.close()


# ------------------------------------------------------------------ scoring
def test_win_probability_is_symmetric_and_bounded() -> None:
    assert win_probability(0) == pytest.approx(0.5)
    assert win_probability(500) + win_probability(-500) == pytest.approx(1.0)
    assert 0.0 < win_probability(-100_000) < win_probability(100_000) < 1.0


def test_win_probability_fairness_in_decided_positions() -> None:
    """The same centipawn loss must matter less when the game is already decided."""
    equal_loss = (win_probability(0) - win_probability(-200)) * 100
    winning_loss = (win_probability(900) - win_probability(700)) * 100
    assert equal_loss > 3 * winning_loss

    assert classify_loss(200, equal_loss, played_is_best=False) == "blunder"
    assert classify_loss(200, winning_loss, played_is_best=False) == "inaccuracy"


def test_label_thresholds() -> None:
    assert classify_loss(0, 0.0, played_is_best=True) == "best"
    assert classify_loss(10, 1.0, played_is_best=False) == "good"
    assert classify_loss(40, 5.0, played_is_best=False) == "inaccuracy"
    assert classify_loss(120, 12.0, played_is_best=False) == "mistake"
    assert classify_loss(400, 40.0, played_is_best=False) == "blunder"


def test_at_least_raises_but_never_lowers() -> None:
    assert at_least("good", "mistake") == "mistake"
    assert at_least("blunder", "mistake") == "blunder"


# ------------------------------------------------------- board-level queries
def test_static_exchange_eval_sees_through_recaptures() -> None:
    # Rook takes a pawn defended by a knight: wins 100, loses 500.
    board = chess.Board("4k3/8/8/8/1n6/8/2p5/2R1K3 w - - 0 1")
    assert bl.static_exchange_eval(board, board.parse_san("Rxc2")) == 100 - 500

    # Rook takes a free knight.
    board2 = chess.Board("4k3/8/8/8/2n5/8/8/2R1K3 w - - 0 1")
    assert bl.static_exchange_eval(board2, board2.parse_san("Rxc4")) == 320


def test_hanging_detection() -> None:
    board = chess.Board("4k3/8/8/8/2n5/8/8/2R1K3 w - - 0 1")
    assert bl.worst_hanging(board, chess.BLACK) == 320
    assert bl.worst_hanging(board, chess.WHITE) == 0


def test_fork_pin_skewer_and_back_rank() -> None:
    fork = chess.Board("8/2q1k3/8/8/8/4N3/8/6K1 w - - 0 1")
    move = fork.parse_san("Nd5+")
    after = fork.copy()
    after.push(move)
    assert bl.creates_fork(after, move)

    pin = chess.Board("3k4/3q4/8/8/8/8/8/R3K3 w - - 0 1")
    pin_move = pin.parse_san("Rd1")
    pin_after = pin.copy()
    pin_after.push(pin_move)
    assert bl.creates_pin_or_skewer(pin_after, pin_move) == "pin"

    skewer = chess.Board("r7/8/8/3k4/8/7B/8/4K3 w - - 0 1")
    skewer_move = skewer.parse_san("Bg2+")
    skewer_after = skewer.copy()
    skewer_after.push(skewer_move)
    assert bl.creates_pin_or_skewer(skewer_after, skewer_move) == "skewer"

    mate = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    mate.push_san("Ra8#")
    assert bl.is_back_rank_mate(mate)


def test_game_phase() -> None:
    assert bl.game_phase(chess.Board()) == "opening"
    assert bl.game_phase(chess.Board("4k3/8/4K3/4P3/8/8/8/8 w - - 0 1")) == "endgame"


# ------------------------------------------------------------- motif mapping
@pytest.mark.parametrize(
    ("fen", "played", "best", "expected_motif", "expected_key"),
    [
        ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra7", "Ra8#", "missed_mate", "missed_mate"),
        ("4k3/8/8/8/2n5/8/8/2R1K3 w - - 0 1", "Kf1", "Rxc4", "missed_capture", "missed_captures"),
        ("8/2q1k3/8/8/8/4N3/8/6K1 w - - 0 1", "Kf1", "Nd5+", "missed_fork", "missed_forks"),
        ("3k4/3q4/8/8/8/8/8/R3K3 w - - 0 1", "Kf1", "Rd1", "missed_pin", "missed_pins_skewers"),
        ("r7/8/8/3k4/8/7B/8/4K3 w - - 0 1", "Kf1", "Bg2+", "missed_skewer", "missed_pins_skewers"),
    ],
)
def test_motifs_are_named_correctly(fen: str, played: str, best: str, expected_motif: str, expected_key: str) -> None:
    board = chess.Board(fen)
    found = motifs.detect(board, board.parse_san(played), board.parse_san(best), [])
    assert found.motif == expected_motif
    assert expected_key in found.taxonomy_keys


def test_motifs_only_use_real_taxonomy_keys() -> None:
    from app.weakness.taxonomy import TAXONOMY_KEYS

    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3")
    found = motifs.detect(board, board.parse_san("Nd4"), board.parse_san("Bc5"), [])
    assert found.taxonomy_keys
    assert set(found.taxonomy_keys) <= TAXONOMY_KEYS


def test_best_move_has_no_motif() -> None:
    board = chess.Board()
    move = board.parse_san("e4")
    assert motifs.detect(board, move, move, []).motif is None


def test_opening_principle_motifs() -> None:
    # Queen out early with the minor pieces still at home.
    board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    ctx = motifs.MoveContext(move_number=2, phase="opening")
    found = motifs.detect(board, board.parse_san("Qh5"), board.parse_san("Nf3"), [], ctx)
    assert found.motif == "early_queen"
    assert "opening_principles" in found.taxonomy_keys


# ------------------------------------------------------------------- engine
def test_analyze_returns_best_move_and_ranked_lines(engine: StockfishEngine) -> None:
    result = engine.analyze(chess.STARTING_FEN, multipv=3)
    assert result.best_move in {"e4", "d4", "Nf3", "c4"}
    assert len(result.top_moves) == 3
    scores = [line.score_cp for line in result.top_moves]
    assert scores == sorted(scores, reverse=True)
    assert result.best.pv_san, "the engine must return a principal variation"


def test_analyze_finds_forced_mate(engine: StockfishEngine) -> None:
    result = engine.analyze("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    assert result.best_move == "Ra8#"
    assert result.best.mate_in == 1
    assert result.eval_cp > 9000


def test_analyze_rejects_illegal_positions(engine: StockfishEngine) -> None:
    """An illegal FEN crashes the engine process, so it must never reach it."""
    with pytest.raises(ValueError):
        engine.analyze("8/8/8/3r1b2/8/4P3/8/4K3 w - - 0 1")  # black has no king
    with pytest.raises(ValueError):
        engine.analyze("not a fen at all")


def test_analyze_handles_terminal_positions(engine: StockfishEngine) -> None:
    checkmated = engine.analyze("R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
    assert checkmated.eval_cp < -9000
    stalemate = engine.analyze("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert stalemate.eval_cp == 0


def test_classify_recognises_the_best_move(engine: StockfishEngine) -> None:
    verdict = engine.classify_move("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "Nf3")
    assert verdict.label == "best"
    assert verdict.cp_loss == 0
    assert verdict.detected_motif is None


def test_classify_flags_a_hung_piece(engine: StockfishEngine) -> None:
    verdict = engine.classify_move("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", "Nd4")
    assert verdict.is_mistake
    assert verdict.cp_loss > 50
    assert verdict.detected_motif == "hung_piece"
    assert "hanging_pieces" in verdict.taxonomy_keys


def test_classify_flags_a_missed_mate_even_when_still_winning(engine: StockfishEngine) -> None:
    """Win probability barely moves here, but a missed forced mate must still be taught."""
    verdict = engine.classify_move("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra7")
    assert verdict.win_prob_loss < 20  # the position stays winning
    assert verdict.is_serious  # ...and the coach still flags it
    assert verdict.detected_motif == "missed_mate"


def test_classify_flags_a_missed_free_piece(engine: StockfishEngine) -> None:
    verdict = engine.classify_move("4k3/8/8/8/2n5/8/8/2R1K3 w - - 0 1", "Kf1")
    assert verdict.label == "blunder"
    assert verdict.best_move == "Rxc4"
    assert "missed_captures" in verdict.taxonomy_keys


def test_classify_accepts_uci_as_well_as_san(engine: StockfishEngine) -> None:
    san = engine.classify_move(chess.STARTING_FEN, "e4")
    uci = engine.classify_move(chess.STARTING_FEN, "e2e4")
    assert san.played_move == uci.played_move == "e4"


def test_classify_rejects_illegal_moves(engine: StockfishEngine) -> None:
    with pytest.raises(ValueError):
        engine.classify_move(chess.STARTING_FEN, "e5")
    with pytest.raises(ValueError):
        engine.classify_move(chess.STARTING_FEN, "zz9")


def test_analysis_is_cached(engine: StockfishEngine) -> None:
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"
    first = engine.analyze(fen)
    second = engine.analyze(fen)
    assert first.best_move == second.best_move
    assert first.eval_cp == second.eval_cp


# ---------------------------------------------------------------- sparring
def test_sparring_picks_the_nearest_rating_band() -> None:
    assert nearest_band(980) == 1100
    assert nearest_band(1499) == 1500
    assert nearest_band(2400) == 1900


def test_sparring_returns_a_legal_move_and_names_its_opponent() -> None:
    service = SparringService(seed=1)
    try:
        board = chess.Board()
        for _ in range(6):
            move = service.get_human_move(board.fen(), 1100)
            assert move.opponent_kind in {"maia", "stockfish-limited"}
            board.push_san(move.move_san)
        assert board.fullmove_number > 1
    finally:
        service.close()


def test_sparring_describe_is_honest_about_maia() -> None:
    service = SparringService()
    try:
        described = service.describe()
        if not described["maia_available"]:
            assert described["opponent_kind"] == "stockfish-limited"
            assert "not installed" in str(described["note"])
    finally:
        service.close()
