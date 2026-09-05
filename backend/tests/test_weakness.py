"""Phase 4 acceptance: reviewing a game populates a weakness profile with confidences."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.jobs import JobRunner
from app.services.review import move_accuracy
from app.weakness.model import (
    Evidence,
    WeaknessScore,
    aggregate,
    confidence_from,
    record_failure,
    record_success,
    status_for,
    top_weaknesses,
)

BLUNDER_GAME = """[Event "Club night"]
[White "meena"]
[Black "rival"]
[Result "0-1"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 g6 4. Qf3 Nf6 5. Qb3 Nd4 6. Qc3 Bc5 7. Nf3 Nxf3+
8. gxf3 Qe7 9. Rg1 O-O 10. d3 d5 11. Bxd5 Nxd5 12. exd5 Bf5 13. Bg5 Qd7
14. Nd2 Rae8+ 15. Kf1 Qxd5 0-1"""


# ----------------------------------------------------------- pure scoring
def test_confidence_saturates_rather_than_growing_without_bound() -> None:
    """One blunder is noise; the tenth of the same kind should not be ten times as sure."""
    one = confidence_from(1.6)
    three = confidence_from(4.8)
    ten = confidence_from(16.0)
    assert 0 < one < three < ten < 1.0
    assert ten - three < three - one


def test_successes_reduce_confidence() -> None:
    assert confidence_from(6.0, success_count=0) > confidence_from(6.0, success_count=2)
    assert confidence_from(1.0, success_count=5) == 0.0


def test_status_transitions_require_spaced_successes() -> None:
    assert status_for(0.8, 0) == "active"
    assert status_for(0.4, 2) == "improving"
    assert status_for(0.1, 3) == "retired"
    # High confidence blocks retirement even with successes.
    assert status_for(0.9, 3) == "improving"


def test_aggregate_weighs_severity() -> None:
    blunders = aggregate([Evidence("hanging_pieces", "blunder")])
    inaccuracies = aggregate([Evidence("hanging_pieces", "inaccuracy")])
    assert blunders["hanging_pieces"].confidence > inaccuracies["hanging_pieces"].confidence


def test_aggregate_ignores_keys_outside_the_taxonomy() -> None:
    scores = aggregate([Evidence("not_a_real_weakness", "blunder"), Evidence("back_rank", "mistake")])
    assert "not_a_real_weakness" not in scores
    assert "back_rank" in scores


def test_aggregate_builds_on_a_prior_profile() -> None:
    first = aggregate([Evidence("missed_forks", "mistake")])
    second = aggregate([Evidence("missed_forks", "mistake")], prior=first)
    assert second["missed_forks"].evidence_count == 2
    assert second["missed_forks"].confidence > first["missed_forks"].confidence


def test_failure_reopens_an_improving_weakness() -> None:
    score = WeaknessScore("hanging_pieces", evidence_count=3, evidence_weight=3.0)
    record_success(score)
    record_success(score)
    assert score.status == "improving"
    record_failure(score)
    assert score.status == "active"


def test_top_weaknesses_ranks_by_confidence() -> None:
    scores = aggregate([
        Evidence("hanging_pieces", "blunder"),
        Evidence("hanging_pieces", "blunder"),
        Evidence("missed_forks", "inaccuracy"),
        Evidence("back_rank", "mistake"),
    ])
    ranked = [score.taxonomy_key for score in top_weaknesses(scores, limit=2)]
    assert ranked[0] == "hanging_pieces"
    assert len(ranked) == 2


def test_retired_weaknesses_are_not_taught() -> None:
    scores = {"back_rank": WeaknessScore("back_rank", evidence_count=1, status="retired", confidence=0.1)}
    assert top_weaknesses(scores) == []


def test_move_accuracy_curve() -> None:
    assert move_accuracy(0.0) == pytest.approx(100.0)
    assert move_accuracy(3.0) > move_accuracy(10.0) > move_accuracy(40.0)
    assert 0.0 <= move_accuracy(100.0) <= 100.0


# --------------------------------------------------------------- job runner
def test_job_runner_reports_progress_and_completion() -> None:
    runner = JobRunner(max_workers=1)
    try:
        def work(job_id: str | None = None) -> dict[str, int]:
            runner.report_progress(job_id or "", 3, 5)
            return {"answer": 42}

        assert runner.submit("job-a", work) is True
        final = runner.wait_for("job-a", timeout=15)
        assert final["state"] == "done"
        assert final["result"] == {"answer": 42}
    finally:
        runner.shutdown()


def test_job_runner_records_failures() -> None:
    runner = JobRunner(max_workers=1)
    try:
        def boom(job_id: str | None = None) -> None:
            raise RuntimeError("engine exploded")

        runner.submit("job-b", boom)
        final = runner.wait_for("job-b", timeout=15)
        assert final["state"] == "failed"
        assert "engine exploded" in final["error"]
    finally:
        runner.shutdown()


# ---------------------------------------------------------------- the API
@pytest.mark.slow
def test_review_populates_the_weakness_profile(auth_client: TestClient) -> None:
    """The end-to-end acceptance criterion for this phase."""
    game_id = auth_client.post(
        "/api/games/import/pgn", json={"pgn": BLUNDER_GAME, "user_color": "white"}
    ).json()["imported"][0]["id"]

    started = auth_client.post(f"/api/games/{game_id}/review")
    assert started.status_code == 202

    from app.services.jobs import get_job_runner

    final = get_job_runner().wait_for(f"review:{game_id}", timeout=300)
    assert final["state"] == "done", final

    review = auth_client.get(f"/api/games/{game_id}/review").json()
    assert review["state"] == "done"
    assert review["accuracy"] is not None and 0 < review["accuracy"] < 100
    assert len(review["moves"]) == 15  # White's moves only
    assert any(move["move_label"] == "blunder" for move in review["moves"])

    labelled = [move for move in review["moves"] if move["taxonomy_keys"]]
    assert labelled, "mistakes must carry taxonomy keys"
    assert all(move["taxonomy_labels"] for move in labelled)

    weaknesses = auth_client.get("/api/weaknesses").json()
    assert weaknesses, "reviewing a game must produce a visible weakness profile"
    assert weaknesses[0]["confidence"] > 0
    assert weaknesses[0]["teaching_topic"]
    keys = {weakness["taxonomy_key"] for weakness in weaknesses}
    assert "hanging_pieces" in keys
    # Sorted strongest-first.
    confidences = [weakness["confidence"] for weakness in weaknesses]
    assert confidences == sorted(confidences, reverse=True)


def test_review_of_another_users_game_is_rejected(auth_client: TestClient, client: TestClient) -> None:
    game_id = auth_client.post("/api/games/import/pgn", json={"pgn": BLUNDER_GAME}).json()["imported"][0]["id"]
    other = client.post(
        "/api/auth/signup",
        json={"email": "nosy@example.com", "password": "another-password", "display_name": "Nosy"},
    ).json()
    res = client.post(f"/api/games/{game_id}/review", headers={"Authorization": f"Bearer {other['access_token']}"})
    assert res.status_code == 404


def test_weaknesses_start_empty(auth_client: TestClient) -> None:
    assert auth_client.get("/api/weaknesses").json() == []
