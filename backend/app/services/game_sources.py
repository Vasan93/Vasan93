"""Fetch a player's public games from Lichess or Chess.com.

Real games are far more valuable for seeding a weakness profile than puzzles alone,
so importing by username is the fastest path to a useful coaching plan.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.logging import get_logger
from app.services.pgn import split_pgn_collection

log = get_logger(__name__)

USER_AGENT = "GrandmasterAI/0.1 (chess coaching app)"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
MAX_GAMES = 20


class GameSourceError(RuntimeError):
    """The remote service could not give us games. The message is shown to the user."""


@dataclass(frozen=True)
class FetchedGames:
    source: str
    username: str
    pgns: list[str]


def _client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True), True


def _raise_for_common(response: httpx.Response, service: str, username: str) -> None:
    if response.status_code == 404:
        raise GameSourceError(f"{service} has no public player called “{username}”.")
    if response.status_code == 429:
        raise GameSourceError(f"{service} is rate limiting us. Try again in a minute.")
    if response.status_code >= 400:
        raise GameSourceError(f"{service} returned an error ({response.status_code}).")


def fetch_lichess_games(username: str, max_games: int = 10, client: httpx.Client | None = None) -> FetchedGames:
    """Recent rated games from Lichess, newest first."""
    http, owned = _client(client)
    try:
        response = http.get(
            f"https://lichess.org/api/games/user/{username}",
            params={"max": min(max_games, MAX_GAMES), "rated": "true", "clocks": "false", "evals": "false"},
            headers={"Accept": "application/x-chess-pgn"},
        )
        _raise_for_common(response, "Lichess", username)
        pgns = split_pgn_collection(response.text, limit=max_games)
    except httpx.HTTPError as exc:
        raise GameSourceError(f"Could not reach Lichess: {exc}") from exc
    finally:
        if owned:
            http.close()

    if not pgns:
        raise GameSourceError(f"“{username}” has no public games on Lichess yet.")
    return FetchedGames(source="lichess", username=username, pgns=pgns)


def fetch_chesscom_games(username: str, max_games: int = 10, client: httpx.Client | None = None) -> FetchedGames:
    """Recent games from the player's most recent Chess.com monthly archives."""
    http, owned = _client(client)
    try:
        archives_response = http.get(f"https://api.chess.com/pub/player/{username.lower()}/games/archives")
        _raise_for_common(archives_response, "Chess.com", username)
        archives = archives_response.json().get("archives", [])
        if not archives:
            raise GameSourceError(f"“{username}” has no public games on Chess.com yet.")

        pgns: list[str] = []
        # Newest month first; step back until we have enough games.
        for archive_url in reversed(archives[-6:]):
            month_response = http.get(archive_url)
            _raise_for_common(month_response, "Chess.com", username)
            games = month_response.json().get("games", [])
            for game in reversed(games):
                pgn = game.get("pgn")
                if pgn:
                    pgns.append(pgn)
                if len(pgns) >= min(max_games, MAX_GAMES):
                    break
            if len(pgns) >= min(max_games, MAX_GAMES):
                break
    except httpx.HTTPError as exc:
        raise GameSourceError(f"Could not reach Chess.com: {exc}") from exc
    except ValueError as exc:
        raise GameSourceError("Chess.com sent a response we could not read.") from exc
    finally:
        if owned:
            http.close()

    if not pgns:
        raise GameSourceError(f"“{username}” has no public games on Chess.com yet.")
    return FetchedGames(source="chess.com", username=username, pgns=pgns)


def fetch_games(platform: str, username: str, max_games: int = 10, client: httpx.Client | None = None) -> FetchedGames:
    username = username.strip()
    if not username:
        raise GameSourceError("Enter a username first.")
    if platform == "lichess":
        return fetch_lichess_games(username, max_games, client)
    if platform in ("chess.com", "chesscom"):
        return fetch_chesscom_games(username, max_games, client)
    raise GameSourceError(f"Unknown platform: {platform}")
