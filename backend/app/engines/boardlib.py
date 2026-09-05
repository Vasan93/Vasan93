"""Board queries used for motif detection.

Pure `python-chess`: no engine, no LLM. These answer questions the engine's numbers
cannot, such as *why* a move lost material.
"""
from __future__ import annotations

import chess

PIECE_VALUE: dict[chess.PieceType, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20_000,
}

MINOR_OR_BETTER = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)


def piece_value(piece: chess.Piece | None) -> int:
    return PIECE_VALUE[piece.piece_type] if piece else 0


def captured_value(board: chess.Board, move: chess.Move) -> int:
    """Value of the piece a move captures, en passant included."""
    if board.is_en_passant(move):
        return PIECE_VALUE[chess.PAWN]
    return piece_value(board.piece_at(move.to_square))


def _recapture_gain(board: chess.Board, square: chess.Square, depth: int = 0) -> int:
    """Best material the side to move can win by capturing on `square`, or 0 to decline.

    Recursive and played on a real board, so pins, x-rays and promotions are handled
    correctly. Exchange sequences are short, so the cost is small.
    """
    if depth > 8:
        return 0
    best = 0
    for move in board.legal_moves:
        if move.to_square != square or not board.is_capture(move):
            continue
        gained = captured_value(board, move)
        board.push(move)
        net = gained - _recapture_gain(board, square, depth + 1)
        board.pop()
        best = max(best, net)
    return best


def static_exchange_eval(board: chess.Board, move: chess.Move) -> int:
    """Material the mover nets from a capture, after every sensible recapture.

    Positive means the capture wins material; negative means it loses material.
    """
    if not board.is_capture(move):
        return 0
    gained = captured_value(board, move)
    board.push(move)
    net = gained - _recapture_gain(board, move.to_square)
    board.pop()
    return net


def hanging_pieces(board: chess.Board, color: chess.Color) -> list[tuple[chess.Square, int]]:
    """Squares where `color` has a piece the opponent can profitably capture."""
    found: list[tuple[chess.Square, int]] = []
    if board.turn != (not color):
        probe = board.copy(stack=False)
        probe.turn = not color
        if probe.is_valid():
            board = probe
    for move in board.legal_moves:
        if not board.is_capture(move):
            continue
        victim = board.piece_at(move.to_square)
        if victim is None or victim.color != color:
            continue
        gain = static_exchange_eval(board, move)
        if gain > 0:
            found.append((move.to_square, gain))
    return sorted(set(found), key=lambda pair: -pair[1])


def worst_hanging(board: chess.Board, color: chess.Color) -> int:
    """Material `color` stands to lose to a capture right now."""
    hanging = hanging_pieces(board, color)
    return hanging[0][1] if hanging else 0


def creates_fork(board_after: chess.Board, move: chess.Move) -> bool:
    """True when the piece that just moved attacks two or more valuable targets."""
    attacker = board_after.piece_at(move.to_square)
    if attacker is None:
        return False
    attacker_worth = PIECE_VALUE[attacker.piece_type]
    targets = 0
    for square in board_after.attacks(move.to_square):
        victim = board_after.piece_at(square)
        if victim is None or victim.color == attacker.color:
            continue
        if victim.piece_type == chess.KING or PIECE_VALUE[victim.piece_type] >= attacker_worth:
            targets += 1
    if targets < 2:
        return False
    # A "fork" that simply hangs the forking piece is not a fork worth teaching.
    return worst_hanging(board_after, attacker.color) < attacker_worth


def _aligned_behind(board: chess.Board, slider: chess.Square) -> list[tuple[chess.Piece, chess.Piece]]:
    """(front, back) enemy pairs standing on one ray from a sliding piece."""
    piece = board.piece_at(slider)
    if piece is None or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return []
    directions = {
        chess.BISHOP: (9, 7, -7, -9),
        chess.ROOK: (8, 1, -1, -8),
        chess.QUEEN: (9, 8, 7, 1, -1, -7, -8, -9),
    }[piece.piece_type]

    pairs: list[tuple[chess.Piece, chess.Piece]] = []
    for step in directions:
        square = slider
        seen: list[chess.Piece] = []
        while True:
            previous_file = chess.square_file(square)
            square += step
            if not 0 <= square <= 63:
                break
            # Reject wraps around the board edge.
            if abs(chess.square_file(square) - previous_file) > 1:
                break
            occupant = board.piece_at(square)
            if occupant is None:
                continue
            if occupant.color == piece.color:
                break
            seen.append(occupant)
            if len(seen) == 2:
                pairs.append((seen[0], seen[1]))
                break
    return pairs


def creates_pin_or_skewer(board_after: chess.Board, move: chess.Move) -> str | None:
    """Return "pin", "skewer" or None for the piece that just moved."""
    for front, back in _aligned_behind(board_after, move.to_square):
        front_worth = PIECE_VALUE[front.piece_type]
        back_worth = PIECE_VALUE[back.piece_type]
        if front.piece_type == chess.KING and back_worth >= PIECE_VALUE[chess.KNIGHT]:
            return "skewer"
        if back.piece_type == chess.KING or back_worth > front_worth:
            return "pin"
    return None


def creates_discovered_attack(board_before: chess.Board, move: chess.Move) -> bool:
    """True when moving a piece opens a line for a friendly slider onto a valuable target."""
    mover = board_before.turn
    board_after = board_before.copy(stack=False)
    board_after.push(move)

    def valuable_attacks(board: chess.Board, exclude: chess.Square | None) -> set[tuple[chess.Square, chess.Square]]:
        found = set()
        for square in board.pieces(chess.BISHOP, mover) | board.pieces(chess.ROOK, mover) | board.pieces(chess.QUEEN, mover):
            if square == exclude:
                continue
            for target in board.attacks(square):
                victim = board.piece_at(target)
                if victim and victim.color != mover and PIECE_VALUE[victim.piece_type] >= PIECE_VALUE[chess.KNIGHT]:
                    found.add((square, target))
        return found

    before = valuable_attacks(board_before, move.from_square)
    after = valuable_attacks(board_after, move.to_square)
    return bool(after - before)


def is_back_rank_mate(board: chess.Board) -> bool:
    """True when the position is mate with the king stuck on its own back rank."""
    if not board.is_checkmate():
        return False
    loser = board.turn
    king_square = board.king(loser)
    if king_square is None:
        return False
    back_rank = 0 if loser == chess.WHITE else 7
    if chess.square_rank(king_square) != back_rank:
        return False
    # Its own pawns must be blocking the escape squares in front of it.
    forward = 8 if loser == chess.WHITE else -8
    for offset in (-1, 0, 1):
        square = king_square + forward + offset
        if not 0 <= square <= 63 or abs(chess.square_file(square) - chess.square_file(king_square)) > 1:
            continue
        blocker = board.piece_at(square)
        if blocker and blocker.color == loser and blocker.piece_type == chess.PAWN:
            return True
    return False


# --------------------------------------------------------------------- phase
def non_pawn_material(board: chess.Board) -> int:
    total = 0
    for piece_type in MINOR_OR_BETTER:
        total += PIECE_VALUE[piece_type] * (
            len(board.pieces(piece_type, chess.WHITE)) + len(board.pieces(piece_type, chess.BLACK))
        )
    return total


def game_phase(board: chess.Board) -> str:
    """opening | middlegame | endgame, from material and development."""
    material = non_pawn_material(board)
    if material <= 1900:
        return "endgame"
    if board.fullmove_number <= 12 and material >= 5000:
        return "opening"
    return "middlegame"


def is_developing_move(board_before: chess.Board, move: chess.Move) -> bool:
    piece = board_before.piece_at(move.from_square)
    if piece is None or piece.piece_type not in (chess.KNIGHT, chess.BISHOP):
        return False
    home_rank = 0 if piece.color == chess.WHITE else 7
    return chess.square_rank(move.from_square) == home_rank


def undeveloped_minor_count(board: chess.Board, color: chess.Color) -> int:
    home_rank = 0 if color == chess.WHITE else 7
    count = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP):
        for square in board.pieces(piece_type, color):
            if chess.square_rank(square) == home_rank:
                count += 1
    return count
