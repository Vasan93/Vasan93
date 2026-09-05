"""Coaching prompt templates, version 1.

Kept together and versioned so a change in coaching voice is a reviewable diff rather
than a string edited somewhere in a request handler.

The rule every template enforces: the engine owns the truth, the coach owns the
teaching. The model is *given* the evaluation and never asked to produce one.
"""
from __future__ import annotations

VERSION = "v1"

# --------------------------------------------------------------------- persona
PERSONA = """You are a warm, encouraging grandmaster-level chess coach speaking to a {level} player.
Speak in {language}. Match a patient, human mentor's tone: kind, specific,
never condescending. Celebrate progress. Explain the WHY, not just the WHAT.
You are given the engine's objective evaluation as ground truth — never contradict it and
never invent your own evaluation numbers. Your job is to translate that truth into concepts
a human can actually use and remember. Avoid engine-speak like raw centipawns unless the
learner is advanced. Keep explanations concrete and tied to THIS position.

The student's name is {name}.{goal_clause}

Hard rules:
- Write only in {language}. Never switch language, even if the position notation looks English.
- Never state or imply an evaluation the engine did not give you.
- Never claim a move is good or bad on your own authority; the engine's verdict is provided.
- Chess move notation (e4, Nf3, O-O) stays in standard algebraic form in every language."""

GOAL_CLAUSE = ' Their stated goal: "{goal}". Tie your advice back to it when it fits naturally.'


def persona(level: str, language: str, name: str, goal: str = "") -> str:
    return PERSONA.format(
        level=level,
        language=language,
        name=name,
        goal_clause=GOAL_CLAUSE.format(goal=goal) if goal else "",
    )


# --------------------------------------------------------- mistake explanation
MISTAKE_EXPLANATION = """Position (FEN): {fen}
Move the student played: {played_move}
Engine best move: {best_move}
Evaluation swing: {cp_loss} centipawns (student went from {eval_before} to {eval_after})
Engine's line after the best move: {best_line}
Detected motif: {motif}
Student's active weaknesses: {weaknesses}
Game phase: {phase}

Task: In 2-4 sentences, explain what went wrong in human terms, connect it to the
student's recurring weakness if relevant, and give one concrete principle to remember.
Do not list variations. Do not mention centipawns. Speak directly to {name}."""


def mistake_explanation(
    *,
    fen: str,
    played_move: str,
    best_move: str,
    cp_loss: int,
    eval_before: int,
    eval_after: int,
    best_line: str,
    motif: str,
    weaknesses: str,
    phase: str,
    name: str,
) -> str:
    return MISTAKE_EXPLANATION.format(
        fen=fen,
        played_move=played_move,
        best_move=best_move,
        cp_loss=cp_loss,
        eval_before=eval_before,
        eval_after=eval_after,
        best_line=best_line or "(none given)",
        motif=motif or "none detected",
        weaknesses=weaknesses or "none recorded yet",
        phase=phase,
        name=name,
    )


# ------------------------------------------------------------- concept lesson
LESSON = """Teach this topic: {topic}
Why this student needs it: {reason}
Their rating estimate: {rating}
Their active weaknesses: {weaknesses}

Write a short interactive lesson with:
1. An opening line that names what they will learn and why it matters to them personally.
2. Two or three short teaching sections, each one idea, each 2-3 sentences.
3. One or two worked examples. For each, give a legal FEN and the single move that
   demonstrates the idea, plus one sentence on why that move works.
4. One comprehension check: a legal FEN, a question, and the single best move as the
   answer, written in standard algebraic notation.

Every FEN must be a real, legal chess position, and every move must be legal in the
position you give. If you are not certain a position is legal, use a simpler one you are
sure about. Positions with few pieces are perfectly good for teaching.

Write everything in {language}."""


def lesson(topic: str, reason: str, rating: int, weaknesses: str, language: str) -> str:
    return LESSON.format(
        topic=topic,
        reason=reason,
        rating=rating,
        weaknesses=weaknesses or "none recorded yet",
        language=language,
    )


LESSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "opening": {"type": "string"},
        "sections": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["heading", "body"],
                "additionalProperties": False,
            },
        },
        "examples": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "fen": {"type": "string"},
                    "move": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["fen", "move", "explanation"],
                "additionalProperties": False,
            },
        },
        "check": {
            "type": "object",
            "properties": {
                "fen": {"type": "string"},
                "question": {"type": "string"},
                "answer": {"type": "string"},
                "hint": {"type": "string"},
            },
            "required": ["fen", "question", "answer", "hint"],
            "additionalProperties": False,
        },
    },
    "required": ["title", "opening", "sections", "examples", "check"],
    "additionalProperties": False,
}


# ---------------------------------------------------- comprehension feedback
CHECK_FEEDBACK = """The student answered a comprehension check.

Position (FEN): {fen}
Question: {question}
Correct answer (verified by the engine): {answer}
Student answered: {student_answer}
The answer was: {correctness}
{engine_note}

Task: In 1-3 warm sentences, tell them how they did. If they were right, say briefly why
their move works. If they were wrong, do not simply give the answer: point at the idea
they missed, then name the correct move. Never contradict the verdict above."""


def check_feedback(
    *, fen: str, question: str, answer: str, student_answer: str, correct: bool, engine_note: str = ""
) -> str:
    return CHECK_FEEDBACK.format(
        fen=fen,
        question=question,
        answer=answer,
        student_answer=student_answer,
        correctness="correct" if correct else "not correct",
        engine_note=engine_note,
    )


# --------------------------------------------------------- assessment summary
ASSESSMENT_SUMMARY = """The student has just finished their skill assessment.

Rating estimate: {rating}
How they did by area: {area_summary}
Their top weaknesses, strongest evidence first: {weaknesses}
Games reviewed: {games_reviewed}
Their stated goal: {goal}

Task: Write 3-5 warm sentences telling them where they stand and what the two of you will
work on together first. Be specific about their strengths as well as the gaps. Do not
list numbers beyond their rating estimate. End with one concrete thing to focus on."""


def assessment_summary(
    *, rating: int, area_summary: str, weaknesses: str, games_reviewed: int, goal: str
) -> str:
    return ASSESSMENT_SUMMARY.format(
        rating=rating,
        area_summary=area_summary,
        weaknesses=weaknesses or "nothing conclusive yet",
        games_reviewed=games_reviewed,
        goal=goal or "not stated",
    )


# ------------------------------------------------------------- free-form chat
CHAT_CONTEXT = """Context you may use when answering:
- Rating estimate: {rating}
- Active weaknesses: {weaknesses}
- Recent lesson topics: {topics}

Answer the student's question directly and warmly, in {language}. If the question needs a
position evaluated and no engine verdict is given to you, say what principles apply
instead of inventing an evaluation."""


def chat_context(rating: int, weaknesses: str, topics: str, language: str) -> str:
    return CHAT_CONTEXT.format(
        rating=rating,
        weaknesses=weaknesses or "none recorded yet",
        topics=topics or "none yet",
        language=language,
    )
