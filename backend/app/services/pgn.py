"""PGN parsing.

Turns a pasted or fetched PGN into the fields the review pipeline needs, and rejects
anything the engine could not analyse.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import chess
import chess.pgn

MAX_PLIES = 400
MAX_PGN_BYTES = 512_000


class PgnError(ValueError):
    """The PGN could not be read as a chess game."""


_RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}
_HEADER_LINE = re.compile(r"^\s*\[.*\]\s*$", re.MULTILINE)
_BRACE_COMMENT = re.compile(r"\{[^}]*\}")
_LINE_COMMENT = re.compile(r";[^\n]*")
_NAG = re.compile(r"\$\d+")
_MOVE_NUMBER = re.compile(r"\b\d+\.(\.\.)?")


def _strip_variations(text: str) -> str:
    """Remove parenthesised variation lines, honouring nesting."""
    out: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return "".join(out)


def count_movetext_tokens(pgn_text: str) -> int:
    """Count the move tokens written in the PGN, ignoring comments and variations.

    `python-chess` silently skips tokens it cannot parse, so a corrupted PGN would
    otherwise import as a shorter game that was never played. Comparing this count with
    the moves actually parsed turns that into a visible error.
    """
    body = _HEADER_LINE.sub("", pgn_text)
    body = _BRACE_COMMENT.sub(" ", body)
    body = _LINE_COMMENT.sub(" ", body)
    body = _strip_variations(body)
    body = _NAG.sub(" ", body)
    body = _MOVE_NUMBER.sub(" ", body)
    tokens = [tok for tok in body.split() if tok not in _RESULT_TOKENS and tok != "..."]
    return len(tokens)


@dataclass
class ParsedMove:
    ply: int
    move_number: int
    side: str  # white | black
    fen_before: str
    san: str
    uci: str


@dataclass
class ParsedGame:
    pgn: str
    white: str
    black: str
    result: str
    played_at: datetime | None
    event: str
    moves: list[ParsedMove] = field(default_factory=list)
    termination: str = ""

    @property
    def ply_count(self) -> int:
        return len(self.moves)

    def color_for(self, player: str) -> str | None:
        """Which side a named player had, or None if the name does not appear."""
        target = player.strip().lower()
        if not target:
            return None
        if self.white.lower() == target:
            return "white"
        if self.black.lower() == target:
            return "black"
        return None

    def result_for(self, color: str) -> str:
        """win | loss | draw | unknown, from one side's point of view."""
        if self.result == "1/2-1/2":
            return "draw"
        if self.result == "1-0":
            return "win" if color == "white" else "loss"
        if self.result == "0-1":
            return "win" if color == "black" else "loss"
        return "unknown"


def _parse_date(headers: chess.pgn.Headers) -> datetime | None:
    raw_date = headers.get("UTCDate") or headers.get("Date") or ""
    raw_time = headers.get("UTCTime") or "00:00:00"
    raw_date = raw_date.replace(".", "-")
    if "?" in raw_date or not raw_date:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(f"{raw_date} {raw_time}".strip(), fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_pgn(pgn_text: str) -> ParsedGame:
    """Parse a single game. Raises PgnError on anything unusable."""
    if not pgn_text or not pgn_text.strip():
        raise PgnError("The PGN is empty.")
    if len(pgn_text.encode("utf-8")) > MAX_PGN_BYTES:
        raise PgnError("That PGN is too large to import.")

    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
    except Exception as exc:  # python-chess raises a variety of parse errors
        raise PgnError(f"Could not read that PGN: {exc}") from exc
    if game is None:
        raise PgnError("No game found in that PGN.")
    if game.errors:
        raise PgnError(f"That PGN has errors: {game.errors[0]}")

    headers = game.headers
    board = game.board()
    if board.fen() != chess.STARTING_FEN and not headers.get("FEN"):
        raise PgnError("Only games from the standard starting position can be imported yet.")

    moves: list[ParsedMove] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        if ply > MAX_PLIES:
            raise PgnError("That game is unusually long; import it in parts.")
        if move not in board.legal_moves:
            raise PgnError(f"Illegal move at ply {ply}: {move.uci()}")
        moves.append(
            ParsedMove(
                ply=ply,
                move_number=board.fullmove_number,
                side="white" if board.turn == chess.WHITE else "black",
                fen_before=board.fen(),
                san=board.san(move),
                uci=move.uci(),
            )
        )
        board.push(move)

    if not moves:
        raise PgnError("That PGN has no moves to review.")

    written = count_movetext_tokens(pgn_text)
    if written != len(moves):
        raise PgnError(
            f"Could not read every move: the PGN lists {written} moves but only {len(moves)} parsed. "
            "The file looks corrupted or truncated."
        )

    return ParsedGame(
        pgn=pgn_text.strip(),
        white=headers.get("White", "White"),
        black=headers.get("Black", "Black"),
        result=headers.get("Result", "*"),
        played_at=_parse_date(headers),
        event=headers.get("Event", ""),
        termination=headers.get("Termination", ""),
        moves=moves,
    )


def split_pgn_collection(pgn_text: str, limit: int = 20) -> list[str]:
    """Split a multi-game PGN file into individual game texts.

    The original characters are sliced out rather than re-serialised through
    `python-chess`. Re-serialising would quietly drop any token the library failed to
    parse, defeating the movetext check in `parse_pgn`.
    """
    stream = io.StringIO(pgn_text)
    boundaries: list[int] = []
    while len(boundaries) <= limit:
        try:
            headers = chess.pgn.read_headers(stream)
        except Exception:
            break
        if headers is None:
            break
        boundaries.append(stream.tell())

    if not boundaries:
        text = pgn_text.strip()
        return [text] if text else []

    # `read_headers` stops just before each game's movetext, so a game spans from the
    # start of its own header block to the start of the next one.
    starts = [0, *boundaries[:-1]]
    games = [pgn_text[begin:boundaries[index]].strip() for index, begin in enumerate(starts)]
    tail = pgn_text[boundaries[-1]:].strip()
    if tail:
        games.append(tail)

    # The first slice ends before the first movetext; fold it into the game it belongs to.
    merged: list[str] = []
    for chunk in games:
        if merged and not chunk.startswith("["):
            merged[-1] = f"{merged[-1]}\n\n{chunk}"
        else:
            merged.append(chunk)
    return [game for game in merged if game][:limit]


def replay_fens(pgn_text: str) -> list[str]:
    """Every position in the game, starting position first. Used by the board viewer."""
    parsed = parse_pgn(pgn_text)
    fens = [move.fen_before for move in parsed.moves]
    board = chess.Board(fens[0])
    for move in parsed.moves:
        board.push_uci(move.uci)
    fens.append(board.fen())
    return fens
