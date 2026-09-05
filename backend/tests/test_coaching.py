"""Phase 5 acceptance: clicking a mistake yields a warm, correct explanation in the
learner's language, tied to a weakness -- and the model never decides chess facts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.coaching.brain import BrainRefusal, ClaudeBrain, LearnerContext, TemplateBrain
from app.coaching.prompts import v1
from app.coaching.validation import grade_answer, ground_answer, legal_move, legal_position, validate_lesson
from app.engines.stockfish import StockfishEngine

BACK_RANK = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"

BLUNDER_GAME = """[Event "Club night"]
[White "meena"]
[Black "rival"]
[Result "0-1"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 g6 4. Qf3 Nf6 5. Qb3 Nd4 6. Qc3 Bc5 7. Nf3 Nxf3+
8. gxf3 Qe7 9. Rg1 O-O 10. d3 d5 11. Bxd5 Nxd5 12. exd5 Bf5 13. Bg5 Qd7
14. Nd2 Rae8+ 15. Kf1 Qxd5 0-1"""


# --------------------------------------------------------- a stand-in for the SDK
@dataclass
class FakeBlock:
    text: str
    type: str = "text"


@dataclass
class FakeUsage:
    input_tokens: int = 120
    output_tokens: int = 45


@dataclass
class FakeResponse:
    content: list[FakeBlock]
    stop_reason: str = "end_turn"
    stop_details: Any = None
    model: str = "claude-opus-5"
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self, reply: str, stop_reason: str = "end_turn") -> None:
        self.reply = reply
        self.stop_reason = stop_reason
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return FakeResponse(content=[FakeBlock(self.reply)], stop_reason=self.stop_reason)


class FakeClient:
    def __init__(self, reply: str, stop_reason: str = "end_turn") -> None:
        self.messages = FakeMessages(reply, stop_reason)
        self.beta = type("Beta", (), {"messages": self.messages})()


@pytest.fixture(scope="module")
def engine() -> StockfishEngine:
    eng = StockfishEngine(depth=12, seconds=0.25)
    if not eng.available:
        pytest.skip("Stockfish binary not installed")
    yield eng
    eng.close()


@pytest.fixture
def learner() -> LearnerContext:
    return LearnerContext(
        name="Meena", language="Tamil", rating=950, goal="Reach 1500", weaknesses=["Hanging pieces"]
    )


MISTAKE_FACTS = {
    "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
    "played_move": "Nd4",
    "best_move": "Nf6",
    "best_line": ["Nf6", "d3", "Bc5"],
    "cp_loss": 110,
    "eval_cp_before": -20,
    "eval_cp_after": -130,
    "detected_motif": "hung_piece",
    "phase": "opening",
}


# --------------------------------------------------------------------- prompts
def test_persona_names_the_language_and_forbids_switching(learner: LearnerContext) -> None:
    persona = v1.persona(learner.level, learner.language, learner.name, learner.goal)
    assert "Tamil" in persona
    assert "Never switch language" in persona
    assert "Reach 1500" in persona
    assert "never invent" in persona.lower()


def test_mistake_prompt_supplies_the_evaluation_rather_than_asking_for_one() -> None:
    prompt = v1.mistake_explanation(
        fen=MISTAKE_FACTS["fen"],
        played_move="Nd4",
        best_move="Nf6",
        cp_loss=110,
        eval_before=-20,
        eval_after=-130,
        best_line="Nf6 d3 Bc5",
        motif="hung_piece",
        weaknesses="Hanging pieces",
        phase="opening",
        name="Meena",
    )
    assert "Engine best move: Nf6" in prompt
    assert "110 centipawns" in prompt
    assert "Do not mention centipawns" in prompt
    assert "Hanging pieces" in prompt


def test_level_scales_with_rating() -> None:
    assert LearnerContext(rating=700).level == "beginner"
    assert LearnerContext(rating=1200).level == "improving club"
    assert LearnerContext(rating=1600).level == "intermediate"
    assert LearnerContext(rating=2000).level == "advanced"


# ---------------------------------------------------------------- Claude path
def test_claude_brain_sends_the_expected_request(learner: LearnerContext) -> None:
    client = FakeClient("Nd4 leaves the knight loose. Count defenders before you move.")
    brain = ClaudeBrain(client=client, model="claude-opus-5")
    response = brain.explain_mistake(learner, MISTAKE_FACTS)

    assert response.source == "claude"
    assert response.text.startswith("Nd4 leaves")
    assert response.input_tokens == 120

    sent = client.messages.calls[0]
    assert sent["model"] == "claude-opus-5"
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["fallbacks"] == "default"
    assert "Tamil" in sent["system"]
    assert "Nd4" in sent["messages"][0]["content"]


def test_claude_lesson_uses_a_structured_schema(learner: LearnerContext) -> None:
    body = {
        "title": "Counting defenders",
        "opening": "Let us look at loose pieces.",
        "sections": [{"heading": "Look first", "body": "Check every piece."}],
        "examples": [{"fen": BACK_RANK, "move": "Ra8#", "explanation": "The king cannot escape."}],
        "check": {"fen": BACK_RANK, "question": "Find mate", "answer": "Ra8#", "hint": "back rank"},
    }
    client = FakeClient(json.dumps(body))
    brain = ClaudeBrain(client=client)
    response = brain.build_lesson(learner, "Counting defenders", "It keeps happening")

    assert response.structured is not None
    assert response.structured["title"] == "Counting defenders"
    sent = client.messages.calls[0]
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert "check" in sent["output_config"]["format"]["schema"]["required"]


def test_claude_refusal_is_raised_not_swallowed(learner: LearnerContext) -> None:
    client = FakeClient("", stop_reason="refusal")
    with pytest.raises(BrainRefusal):
        ClaudeBrain(client=client).explain_mistake(learner, MISTAKE_FACTS)


def test_malformed_lesson_json_is_rejected(learner: LearnerContext) -> None:
    from app.coaching.brain import BrainError

    client = FakeClient("this is not json")
    with pytest.raises(BrainError):
        ClaudeBrain(client=client).build_lesson(learner, "Topic", "Reason")


# ------------------------------------------------------------------ guardrails
def test_illegal_positions_and_moves_are_refused() -> None:
    assert legal_position(BACK_RANK)
    assert not legal_position("8/8/8/3r1b2/8/4P3/8/4K3 w - - 0 1")  # no black king
    assert not legal_position("banana")
    assert legal_move(BACK_RANK, "Ra8#") == "Ra8#"
    assert legal_move(BACK_RANK, "Qz9") is None


def test_the_engine_overrides_the_models_answer_key(engine: StockfishEngine) -> None:
    """The model is not allowed to decide what the right move is."""
    grounded = ground_answer(engine, BACK_RANK, "Ra7")
    assert grounded is not None
    assert grounded.answer_san == "Ra8#"
    assert grounded.corrected is True


def test_validate_lesson_drops_bad_examples_and_fixes_the_key(engine: StockfishEngine) -> None:
    lesson = {
        "title": "Back rank",
        "opening": "x",
        "sections": [],
        "examples": [
            {"fen": BACK_RANK, "move": "Ra8#", "explanation": "mate"},
            {"fen": "banana", "move": "e4", "explanation": "invented"},
        ],
        "check": {"fen": BACK_RANK, "question": "Find mate", "answer": "Rb1", "hint": "back rank"},
    }
    cleaned, report = validate_lesson(lesson, engine)
    assert report.ok
    assert len(cleaned["examples"]) == 1
    assert cleaned["check"]["answer"] == "Ra8#"
    assert any("illegal position" in problem for problem in report.problems)
    assert any("not the engine's choice" in problem for problem in report.problems)


def test_grading_uses_the_engine_and_accepts_a_near_best_move(engine: StockfishEngine) -> None:
    correct, best, loss = grade_answer(engine, BACK_RANK, "Ra8#")
    assert correct and best == "Ra8#" and loss == 0

    wrong, best_wrong, loss_wrong = grade_answer(engine, BACK_RANK, "Ra7")
    assert not wrong and best_wrong == "Ra8#" and loss_wrong > 0


# -------------------------------------------------------------------- fallback
def test_template_brain_is_honest_about_language(learner: LearnerContext) -> None:
    response = TemplateBrain().explain_mistake(learner, MISTAKE_FACTS)
    assert response.source == "template"
    assert response.language_fallback is True  # learner asked for Tamil
    assert "Nd4" in response.text and "Nf6" in response.text

    english = TemplateBrain().explain_mistake(LearnerContext(language="English"), MISTAKE_FACTS)
    assert english.language_fallback is False


def test_template_explanation_reflects_the_detected_motif() -> None:
    learner = LearnerContext(language="English")
    hung = TemplateBrain().explain_mistake(learner, MISTAKE_FACTS)
    missed = TemplateBrain().explain_mistake(learner, {**MISTAKE_FACTS, "detected_motif": "missed_mate"})
    assert hung.text != missed.text
    assert "checks" in missed.text.lower()


# ------------------------------------------------------------------- the API
def _reviewed_game(client: TestClient) -> int:
    game_id = client.post(
        "/api/games/import/pgn", json={"pgn": BLUNDER_GAME, "user_color": "white"}
    ).json()["imported"][0]["id"]
    client.post(f"/api/games/{game_id}/review")
    from app.services.jobs import get_job_runner

    assert get_job_runner().wait_for(f"review:{game_id}", timeout=300)["state"] == "done"
    return game_id


@pytest.mark.slow
def test_explain_a_reviewed_mistake(auth_client: TestClient) -> None:
    game_id = _reviewed_game(auth_client)
    review = auth_client.get(f"/api/games/{game_id}/review").json()
    blunder = next(move for move in review["moves"] if move["move_label"] == "blunder")

    res = auth_client.post("/api/coach/explain", json={"game_id": game_id, "ply": blunder["ply"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["text"]
    assert blunder["played_move"] in body["text"] or blunder["best_move"] in body["text"]
    assert body["source"] in ("claude", "template")
    # The learner set Tamil, and the template fallback cannot write Tamil.
    assert body["language_fallback"] is (body["source"] == "template")


@pytest.mark.slow
def test_explaining_an_unreviewed_move_is_404(auth_client: TestClient) -> None:
    game_id = auth_client.post("/api/games/import/pgn", json={"pgn": BLUNDER_GAME}).json()["imported"][0]["id"]
    assert auth_client.post("/api/coach/explain", json={"game_id": game_id, "ply": 3}).status_code == 404


@pytest.mark.slow
def test_lesson_from_the_learners_own_games_and_its_check(auth_client: TestClient) -> None:
    _reviewed_game(auth_client)

    created = auth_client.post("/api/coach/lessons", json={"taxonomy_key": "hanging_pieces"})
    assert created.status_code == 201, created.text
    lesson = created.json()
    assert lesson["examples"], "a lesson must have at least one worked example"
    assert lesson["check"] is not None
    assert "answer" not in lesson["check"], "the answer must not be sent before the student tries"

    # Wrong answer first.
    import chess

    board = chess.Board(lesson["check"]["fen"])
    engine_answer = None
    from app.engines.stockfish import get_analysis_engine

    engine_answer = get_analysis_engine().analyze(lesson["check"]["fen"], multipv=2)
    wrong_move = next(
        (line.move_san for line in engine_answer.top_moves[1:] if line.move_san),
        board.san(next(iter(board.legal_moves))),
    )

    wrong = auth_client.post(f"/api/coach/lessons/{lesson['id']}/check", json={"answer": wrong_move})
    assert wrong.status_code == 200
    assert wrong.json()["best_move"] == engine_answer.best.move_san

    right = auth_client.post(
        f"/api/coach/lessons/{lesson['id']}/check", json={"answer": engine_answer.best.move_san}
    )
    assert right.json()["correct"] is True
    assert right.json()["feedback"]


def test_lesson_without_evidence_is_refused(auth_client: TestClient) -> None:
    """No made-up teaching material: without evidence there is nothing honest to teach."""
    res = auth_client.post("/api/coach/lessons", json={"taxonomy_key": "rook_endgames"})
    assert res.status_code == 409
    assert "not enough material" in res.json()["detail"]


def test_unknown_lesson_topic_is_rejected(auth_client: TestClient) -> None:
    assert auth_client.post("/api/coach/lessons", json={"taxonomy_key": "invented_topic"}).status_code == 400


def test_illegal_check_answer_is_rejected(auth_client: TestClient) -> None:
    from app.models import Lesson

    body = {
        "title": "t", "opening": "o", "sections": [], "examples": [],
        "check": {"fen": BACK_RANK, "question": "q", "answer": "Ra8#", "hint": "h"},
        "intro": "", "source": "template",
    }
    me = auth_client.get("/api/auth/me").json()
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        lesson = Lesson(
            user_id=me["id"], topic="back_rank", language="English",
            transcript=json.dumps(body), comprehension_checks=json.dumps([body["check"]]),
        )
        db.add(lesson)
        db.commit()
        lesson_id = lesson.id

    res = auth_client.post(f"/api/coach/lessons/{lesson_id}/check", json={"answer": "Qz9"})
    assert res.status_code == 400


@pytest.mark.slow
def test_every_coaching_call_is_recorded_for_review(auth_client: TestClient) -> None:
    game_id = _reviewed_game(auth_client)
    review = auth_client.get(f"/api/games/{game_id}/review").json()
    blunder = next(move for move in review["moves"] if move["move_label"] == "blunder")
    auth_client.post("/api/coach/explain", json={"game_id": game_id, "ply": blunder["ply"]})

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import CoachingLog

    with SessionLocal() as db:
        logs = db.scalars(select(CoachingLog).where(CoachingLog.kind == "mistake")).all()
    assert logs, "coaching output must be logged for quality review"
    assert logs[0].response
    assert logs[0].prompt_version == "v1"


def test_chat_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/coach/chat", json={"message": "hello"}).status_code == 401


def test_fallback_names_the_language_the_learner_asked_for(learner: LearnerContext) -> None:
    """The notice must say Tamil, not the language the fallback happened to write in."""
    response = TemplateBrain().explain_mistake(learner, MISTAKE_FACTS)
    assert response.language == "English"
    assert response.requested_language == "Tamil"
    assert response.language_fallback is True
