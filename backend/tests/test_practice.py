"""Phase 8 acceptance: a user can play a full game against the sparring opponent and get
a coached review afterwards.
"""
from __future__ import annotations

import chess
import pytest
from fastapi.testclient import TestClient

from app.engines.sparring import SparringService, nearest_band
from app.models import Game, User
from app.practice import service


@pytest.fixture
def sparring() -> SparringService:
    engine = SparringService(seed=5)
    yield engine
    engine.close()


def _user(db) -> User:
    from sqlalchemy import select

    user = db.scalar(select(User))
    user.current_rating_estimate = 1100
    db.flush()
    return user


# ------------------------------------------------------------------ service
def test_a_new_game_starts_with_the_learner_to_move(auth_client: TestClient, sparring: SparringService) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user(db)
        game, state = service.start_game(db, user, "white", sparring=sparring)
        db.commit()

    assert state.turn == "white"
    assert state.user_color == "white"
    assert state.move_history == []
    assert state.opponent_kind in ("maia", "stockfish-limited")
    assert state.opponent_rating == 1100
    assert game.source == "practice"


def test_playing_black_means_the_opponent_moves_first(auth_client: TestClient, sparring: SparringService) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user(db)
        _game, state = service.start_game(db, user, "black", sparring=sparring)
        db.commit()

    assert len(state.move_history) == 1
    assert state.turn == "black"


def test_each_move_draws_a_reply(auth_client: TestClient, sparring: SparringService) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user(db)
        game, _ = service.start_game(db, user, "white", sparring=sparring)
        state = service.play_move(db, user, game, "e4", sparring=sparring)
        db.commit()

    assert state.move_history[0] == "e4"
    assert len(state.move_history) == 2
    assert state.turn == "white"
    # The resulting position must be reachable and legal.
    board = chess.Board(state.fen)
    assert board.is_valid()


def test_illegal_and_out_of_turn_moves_are_refused(auth_client: TestClient, sparring: SparringService) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user(db)
        game, _ = service.start_game(db, user, "white", sparring=sparring)
        # Nonsense: parses as neither SAN nor UCI.
        with pytest.raises(ValueError, match="not a move"):
            service.play_move(db, user, game, "Zz9", sparring=sparring)
        # Well-formed UCI, but not a legal move in this position.
        with pytest.raises(ValueError, match="not legal"):
            service.play_move(db, user, game, "e2e5", sparring=sparring)
        # A black move while it is White's turn.
        with pytest.raises(ValueError, match="not your turn|not legal"):
            service.play_move(db, user, game, "e7e5", sparring=sparring)
        db.rollback()


def test_a_finished_game_reports_the_outcome(auth_client: TestClient, sparring: SparringService) -> None:
    """Fool's mate: the fastest way to reach a real game-over state."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        user = _user(db)
        game, _ = service.start_game(db, user, "black", sparring=sparring)
        # Drive the position directly so the test does not depend on the opponent's taste.
        board = chess.Board()
        for move in ["f3", "e5", "g4", "Qh4#"]:
            board.push_san(move)
        assert board.is_checkmate()
        assert service._outcome_text(board, "black") == "You won by checkmate."
        assert service._outcome_text(board, "white") == "You were checkmated."
        db.rollback()


def test_the_sparring_band_matches_the_learners_rating() -> None:
    assert nearest_band(1100) == 1100
    assert nearest_band(1450) == 1400 or nearest_band(1450) == 1500


# ---------------------------------------------------------------- the API
def test_play_a_game_through_the_api(auth_client: TestClient) -> None:
    created = auth_client.post("/api/practice/new", json={"color": "white"})
    assert created.status_code == 201, created.text
    state = created.json()
    game_id = state["game_id"]
    assert state["opponent_note"]

    for move in ["e4", "Nf3", "Bc4"]:
        res = auth_client.post(f"/api/practice/{game_id}/move", json={"move": move})
        assert res.status_code == 200, res.text
        state = res.json()
        if state["is_over"]:
            break
    assert len(state["move_history"]) >= 2

    fetched = auth_client.get(f"/api/practice/{game_id}").json()
    assert fetched["move_history"] == state["move_history"]

    current = auth_client.get("/api/practice/current").json()
    assert current["game_id"] == game_id


def test_illegal_move_through_the_api_is_400(auth_client: TestClient) -> None:
    game_id = auth_client.post("/api/practice/new", json={"color": "white"}).json()["game_id"]
    res = auth_client.post(f"/api/practice/{game_id}/move", json={"move": "e5"})
    assert res.status_code == 400


def test_resigning_ends_the_game_and_queues_a_review(auth_client: TestClient) -> None:
    game_id = auth_client.post("/api/practice/new", json={"color": "white"}).json()["game_id"]
    auth_client.post(f"/api/practice/{game_id}/move", json={"move": "e4"})

    resigned = auth_client.post(f"/api/practice/{game_id}/resign").json()
    assert resigned["is_over"] is True
    assert resigned["result"] == "0-1"
    assert "resigned" in resigned["outcome_text"].lower()

    from app.services.jobs import get_job_runner

    final = get_job_runner().wait_for(f"review:{game_id}", timeout=300)
    assert final["state"] == "done", final

    review = auth_client.get(f"/api/games/{game_id}/review").json()
    assert review["state"] == "done"
    assert review["moves"], "a practice game must be reviewed like any other"


def test_practice_games_are_private(auth_client: TestClient, client: TestClient) -> None:
    game_id = auth_client.post("/api/practice/new", json={"color": "white"}).json()["game_id"]
    other = client.post(
        "/api/auth/signup",
        json={"email": "rival@example.com", "password": "another-password", "display_name": "Rival"},
    ).json()
    res = client.get(f"/api/practice/{game_id}", headers={"Authorization": f"Bearer {other['access_token']}"})
    assert res.status_code == 404


def test_practice_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/practice/new", json={"color": "white"}).status_code == 401


def test_current_returns_a_finished_game_so_its_review_can_be_reached(auth_client: TestClient) -> None:
    """After resigning, the learner still needs the result and the link to the review."""
    game_id = auth_client.post("/api/practice/new", json={"color": "white"}).json()["game_id"]
    auth_client.post(f"/api/practice/{game_id}/move", json={"move": "e4"})
    auth_client.post(f"/api/practice/{game_id}/resign")

    current = auth_client.get("/api/practice/current").json()
    assert current is not None, "a finished game must still be reachable"
    assert current["game_id"] == game_id
    assert current["is_over"] is True


def test_resigned_pgn_records_the_resignation_result(auth_client: TestClient) -> None:
    game_id = auth_client.post("/api/practice/new", json={"color": "white"}).json()["game_id"]
    auth_client.post(f"/api/practice/{game_id}/move", json={"move": "e4"})
    auth_client.post(f"/api/practice/{game_id}/resign")

    detail = auth_client.get(f"/api/games/{game_id}").json()
    assert '[Result "0-1"]' in detail["pgn"]
    assert detail["result"] == "0-1"
