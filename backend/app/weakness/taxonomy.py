"""The weakness taxonomy (Section 11).

Weaknesses are *patterns*, never individual blunders. Every mistake the engine layer
detects maps to one or more of these keys, and the curriculum is built around them.
The set is fixed and extensible: adding a key here makes it available to detection,
teaching and the SRS scheduler at once.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Category(StrEnum):
    TACTICAL = "tactical"
    POSITIONAL = "positional"
    ENDGAME = "endgame"
    OPENING = "opening"
    META = "meta"


@dataclass(frozen=True)
class TaxonomyEntry:
    key: str
    label: str
    category: Category
    description: str
    teaching_topic: str
    # Lichess puzzle themes that train this weakness. Used to pick puzzles.
    puzzle_themes: tuple[str, ...] = ()


_ENTRIES: tuple[TaxonomyEntry, ...] = (
    # ---------------------------------------------------------------- tactical
    TaxonomyEntry(
        "hanging_pieces", "Hanging pieces", Category.TACTICAL,
        "Leaving pieces undefended or moving them onto squares the opponent already attacks.",
        "Counting attackers and defenders before you move",
        ("hangingPiece", "capturingDefender"),
    ),
    TaxonomyEntry(
        "missed_captures", "Missed free material", Category.TACTICAL,
        "Not taking material the opponent left undefended.",
        "Scanning for undefended pieces every move",
        ("hangingPiece",),
    ),
    TaxonomyEntry(
        "missed_forks", "Missed forks", Category.TACTICAL,
        "Overlooking moves that attack two targets at once, especially with knights.",
        "Finding forks: one piece, two targets",
        ("fork", "doubleCheck"),
    ),
    TaxonomyEntry(
        "missed_pins_skewers", "Missed pins and skewers", Category.TACTICAL,
        "Overlooking chances to line up two enemy pieces on one rank, file or diagonal.",
        "Pins and skewers: attacking through a piece",
        ("pin", "skewer"),
    ),
    TaxonomyEntry(
        "back_rank", "Back-rank weakness", Category.TACTICAL,
        "Missing back-rank mates, or leaving your own king boxed in behind its pawns.",
        "Back-rank mate and giving your king air",
        ("backRankMate",),
    ),
    TaxonomyEntry(
        "missed_discovered_attacks", "Missed discovered attacks", Category.TACTICAL,
        "Overlooking moves that unleash an attack from a piece behind the one that moves.",
        "Discovered attacks and discovered check",
        ("discoveredAttack",),
    ),
    TaxonomyEntry(
        "missed_mate", "Missed forced mate", Category.TACTICAL,
        "A forced checkmate was available and went unplayed.",
        "Recognising mating patterns",
        ("mate", "mateIn1", "mateIn2", "mateIn3"),
    ),
    TaxonomyEntry(
        "allowed_mate", "Allowed forced mate", Category.TACTICAL,
        "Playing into a position where the opponent has a forced checkmate.",
        "Spotting mate threats against your own king",
        ("mate", "defensiveMove"),
    ),
    # -------------------------------------------------------------- positional
    TaxonomyEntry(
        "piece_development", "Slow development", Category.POSITIONAL,
        "Leaving minor pieces at home, or moving the same piece repeatedly in the opening.",
        "Developing every piece before you attack",
        ("opening",),
    ),
    TaxonomyEntry(
        "king_safety", "King safety", Category.POSITIONAL,
        "Castling too late, opening lines toward your own king, or advancing the pawns in front of it.",
        "Keeping your king safe",
        ("kingsideAttack", "queensideAttack", "attackingF2F7"),
    ),
    TaxonomyEntry(
        "pawn_structure", "Pawn structure", Category.POSITIONAL,
        "Creating doubled, isolated or backward pawns without compensation.",
        "Pawn structure: strengths and weaknesses",
        ("advancedPawn",),
    ),
    TaxonomyEntry(
        "piece_activity", "Passive pieces", Category.POSITIONAL,
        "Leaving pieces on squares where they do little, especially rooks and bishops.",
        "Giving every piece a job",
        ("quietMove",),
    ),
    TaxonomyEntry(
        "center_control", "Neglecting the centre", Category.POSITIONAL,
        "Ignoring the central squares in the opening and early middlegame.",
        "Why the centre decides the game",
        ("opening",),
    ),
    TaxonomyEntry(
        "misplaced_knights", "Misplaced knights", Category.POSITIONAL,
        "Knights on the rim or without a stable outpost.",
        "Knights need outposts",
        ("knightEndgame",),
    ),
    # ----------------------------------------------------------------- endgame
    TaxonomyEntry(
        "king_activity_endgame", "Passive king in the endgame", Category.ENDGAME,
        "Leaving the king on the back rank when it should be marching to the centre.",
        "The king is a fighting piece in the endgame",
        ("endgame", "kingsideAttack"),
    ),
    TaxonomyEntry(
        "pawn_promotion", "Promotion technique", Category.ENDGAME,
        "Mishandling passed pawns: pushing too early, or failing to escort them.",
        "Escorting a passed pawn home",
        ("advancedPawn", "promotion", "pawnEndgame"),
    ),
    TaxonomyEntry(
        "basic_checkmates", "Basic checkmates", Category.ENDGAME,
        "Failing to convert king and queen, or king and rook, against a lone king.",
        "Mating with king and rook, king and queen",
        ("mateIn2", "endgame"),
    ),
    TaxonomyEntry(
        "opposition", "Opposition", Category.ENDGAME,
        "Losing king-and-pawn endings by mishandling the opposition.",
        "The opposition in king and pawn endings",
        ("pawnEndgame", "endgame"),
    ),
    TaxonomyEntry(
        "rook_endgames", "Rook endgames", Category.ENDGAME,
        "Misplacing the rook: passive defence, no cut-off, rook in front of the pawn.",
        "Rook endgame fundamentals",
        ("rookEndgame", "endgame"),
    ),
    # ----------------------------------------------------------------- opening
    TaxonomyEntry(
        "opening_principles", "Opening principles", Category.OPENING,
        "Bringing the queen out early, moving one piece repeatedly, or ignoring development.",
        "The three opening principles",
        ("opening",),
    ),
    TaxonomyEntry(
        "opening_traps", "Common opening traps", Category.OPENING,
        "Walking into well-known traps and early tactics.",
        "Traps every player should know",
        ("opening", "trappedPiece"),
    ),
    # -------------------------------------------------------------------- meta
    TaxonomyEntry(
        "threat_checking", "Not checking the opponent's threat", Category.META,
        "Playing your own plan without asking what the opponent's last move threatened.",
        "Ask what your opponent wants before you move",
        ("defensiveMove", "hangingPiece"),
    ),
    TaxonomyEntry(
        "moving_too_fast", "Moving too fast", Category.META,
        "Errors that come from speed rather than understanding.",
        "Slowing down at the critical moment",
        (),
    ),
    TaxonomyEntry(
        "time_management", "Time management", Category.META,
        "Spending the clock in the wrong places and then rushing the decisive moment.",
        "Spending your clock where it matters",
        (),
    ),
)

TAXONOMY: dict[str, TaxonomyEntry] = {entry.key: entry for entry in _ENTRIES}
TAXONOMY_KEYS: frozenset[str] = frozenset(TAXONOMY)


def entry(key: str) -> TaxonomyEntry:
    return TAXONOMY[key]


def label(key: str) -> str:
    found = TAXONOMY.get(key)
    return found.label if found else key.replace("_", " ")


def by_category(category: Category) -> list[TaxonomyEntry]:
    return [e for e in TAXONOMY.values() if e.category is category]


def validate(keys: list[str]) -> list[str]:
    """Drop anything that is not a real taxonomy key. Detection must never invent keys."""
    return [k for k in keys if k in TAXONOMY_KEYS]
