"""Phase 3 acceptance: import a game and step through it on the board."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.game_sources import GameSourceError, fetch_games
from app.services.pgn import PgnError, count_movetext_tokens, parse_pgn, replay_fens, split_pgn_collection

LEGALL_MATE = """[Event "Casual game"]
[Site "Paris"]
[Date "1750.??.??"]
[White "Legall"]
[Black "Saint Brie"]
[Result "1-0"]

1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5# 1-0"""

SCHOLARS = """[Event "Club night"]
[White "meena"]
[Black "rival"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0"""


# ------------------------------------------------------------------ parsing
def test_parse_pgn_extracts_headers_and_moves() -> None:
    game = parse_pgn(LEGALL_MATE)
    assert game.white == "Legall"
    assert game.black == "Saint Brie"
    assert game.result == "1-0"
    assert game.ply_count == 13
    assert game.moves[0].san == "e4"
    assert game.moves[0].side == "white"
    assert game.moves[-1].san == "Nd5#"


def test_color_and_result_helpers() -> None:
    game = parse_pgn(SCHOLARS)
    assert game.color_for("meena") == "white"
    assert game.color_for("RIVAL") == "black"
    assert game.color_for("someone else") is None
    assert game.result_for("white") == "win"
    assert game.result_for("black") == "loss"


def test_replay_produces_one_more_position_than_moves() -> None:
    fens = replay_fens(SCHOLARS)
    assert len(fens) == parse_pgn(SCHOLARS).ply_count + 1
    assert fens[0].startswith("rnbqkbnr/pppppppp")


def test_annotations_variations_and_nags_are_ignored() -> None:
    annotated = """[White "A"]
[Black "B"]
[Result "*"]

1. e4 {best by test} e5 $1 2. Nf3 (2. Bc4 Nf6 3. d3) 2... Nc6 ; trailing comment
*"""
    assert parse_pgn(annotated).ply_count == 4


def test_truncated_pgn_is_rejected_rather_than_silently_shortened() -> None:
    """python-chess drops tokens it cannot parse; that must not become a shorter game."""
    with pytest.raises(PgnError, match="Could not read every move"):
        parse_pgn("1. e4 e5 2. Ke2 Ke7 3. Qzz")


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "[Event \"x\"]\n\n*", "not a pgn at all"],
)
def test_unusable_pgn_is_rejected(bad: str) -> None:
    with pytest.raises(PgnError):
        parse_pgn(bad)


def test_illegal_move_in_pgn_is_rejected() -> None:
    with pytest.raises(PgnError):
        parse_pgn("[White \"A\"]\n[Black \"B\"]\n\n1. e4 e5 2. Qh8 *")


def test_count_movetext_tokens_ignores_decoration() -> None:
    assert count_movetext_tokens("1. e4 e5 2. Nf3 Nc6 1-0") == 4
    assert count_movetext_tokens("[White \"x\"]\n\n1. e4 {note} e5 $2 (1... c5) 1/2-1/2") == 2


def test_split_collection_finds_each_game() -> None:
    assert len(split_pgn_collection(LEGALL_MATE + "\n\n" + SCHOLARS)) == 2


# ------------------------------------------------------------ remote sources
def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lichess_fetch_parses_concatenated_pgns() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "lichess.org" in str(request.url)
        assert request.headers["Accept"] == "application/x-chess-pgn"
        return httpx.Response(200, text=f"{SCHOLARS}\n\n{LEGALL_MATE}")

    fetched = fetch_games("lichess", "meena", 5, client=_mock_client(handler))
    assert fetched.source == "lichess"
    assert len(fetched.pgns) == 2


def test_chesscom_fetch_walks_archives_newest_first() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/games/archives"):
            return httpx.Response(200, json={"archives": ["https://api.chess.com/x/2026/07", "https://api.chess.com/x/2026/08"]})
        if url.endswith("2026/08"):
            return httpx.Response(200, json={"games": [{"pgn": SCHOLARS}]})
        return httpx.Response(200, json={"games": []})

    fetched = fetch_games("chess.com", "meena", 5, client=_mock_client(handler))
    assert fetched.source == "chess.com"
    assert len(fetched.pgns) == 1


@pytest.mark.parametrize("platform", ["lichess", "chess.com"])
def test_unknown_player_gives_a_readable_error(platform: str) -> None:
    handler = lambda _request: httpx.Response(404)  # noqa: E731
    with pytest.raises(GameSourceError, match="no public player"):
        fetch_games(platform, "nobody-at-all", 5, client=_mock_client(handler))


def test_rate_limit_is_reported_clearly() -> None:
    handler = lambda _request: httpx.Response(429)  # noqa: E731
    with pytest.raises(GameSourceError, match="rate limiting"):
        fetch_games("lichess", "meena", 5, client=_mock_client(handler))


def test_unknown_platform_is_rejected() -> None:
    with pytest.raises(GameSourceError, match="Unknown platform"):
        fetch_games("playchess", "meena", 5)


# ------------------------------------------------------------------ the API
def test_import_pgn_then_step_through_it(auth_client: TestClient) -> None:
    created = auth_client.post("/api/games/import/pgn", json={"pgn": LEGALL_MATE, "user_color": "white"})
    assert created.status_code == 201, created.text
    assert len(created.json()["imported"]) == 1
    game_id = created.json()["imported"][0]["id"]

    detail = auth_client.get(f"/api/games/{game_id}").json()
    assert detail["ply_count"] == 13
    assert len(detail["fens"]) == 14
    assert detail["moves"][0]["san"] == "e4"
    assert detail["outcome"] == "win"
    assert detail["review_status"] == "pending"


def test_import_infers_the_users_colour_from_the_headers(auth_client: TestClient) -> None:
    created = auth_client.post("/api/games/import/pgn", json={"pgn": SCHOLARS, "player_name": "rival"})
    assert created.json()["imported"][0]["user_color"] == "black"
    assert created.json()["imported"][0]["outcome"] == "loss"


def test_import_multi_game_pgn(auth_client: TestClient) -> None:
    created = auth_client.post("/api/games/import/pgn", json={"pgn": LEGALL_MATE + "\n\n" + SCHOLARS})
    assert len(created.json()["imported"]) == 2
    assert len(auth_client.get("/api/games").json()) == 2


def test_import_rejects_a_broken_pgn(auth_client: TestClient) -> None:
    res = auth_client.post("/api/games/import/pgn", json={"pgn": "1. e4 e5 2. Qzz"})
    assert res.status_code == 400


def test_games_are_private_to_their_owner(auth_client: TestClient, client: TestClient) -> None:
    game_id = auth_client.post("/api/games/import/pgn", json={"pgn": SCHOLARS}).json()["imported"][0]["id"]

    other = client.post(
        "/api/auth/signup",
        json={"email": "other@example.com", "password": "another-password", "display_name": "Other"},
    ).json()
    stolen = client.get(f"/api/games/{game_id}", headers={"Authorization": f"Bearer {other['access_token']}"})
    assert stolen.status_code == 404


def test_delete_game(auth_client: TestClient) -> None:
    game_id = auth_client.post("/api/games/import/pgn", json={"pgn": SCHOLARS}).json()["imported"][0]["id"]
    assert auth_client.delete(f"/api/games/{game_id}").status_code == 204
    assert auth_client.get(f"/api/games/{game_id}").status_code == 404


def test_import_requires_authentication(client: TestClient) -> None:
    assert client.post("/api/games/import/pgn", json={"pgn": SCHOLARS}).status_code == 401
