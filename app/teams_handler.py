"""
Teams Bot Framework Handler
============================
Handles incoming messages from Microsoft Teams via Azure Bot Framework.

Setup:
  1. Register a bot in Azure Bot Service (portal.azure.com)
  2. Add the Teams channel
  3. Set the messaging endpoint to:
     https://<your-databricks-app-url>/bot/messages
  4. Store the App ID and Password in Databricks secrets:
     - coworker-agent/teams-app-id
     - coworker-agent/teams-app-password

This handler plugs into the FastAPI app (main.py).
"""

from __future__ import annotations
import json
import logging
import uuid
from typing import Any

import httpx
from fastapi import Request, Response

log = logging.getLogger("coworker.teams")

# Bot Framework OAuth endpoint
_TOKEN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
_BOT_API   = "https://smba.trafficmanager.net/apis"


class TeamsBotHandler:
    """Lightweight Azure Bot Framework handler (no SDK dependency)."""

    def __init__(self, app_id: str, app_password: str):
        self.app_id = app_id
        self.app_password = app_password
        self._token: str | None = None

    # ── OAuth token ───────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.app_id,
                    "client_secret": self.app_password,
                    "scope": "https://api.botframework.com/.default",
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
            return self._token

    # ── Process incoming activity ─────────────────────────────────────────

    async def handle_activity(self, request: Request) -> Response:
        """
        Receive a Bot Framework Activity from Teams, process it through
        the Co-Worker agent, and reply.
        """
        body: dict = await request.json()
        activity_type = body.get("type", "")

        if activity_type != "message":
            return Response(status_code=200)

        text = body.get("text", "").strip()
        if not text:
            return Response(status_code=200)

        # Remove the @mention of the bot (Teams prefixes messages with it)
        for entity in body.get("entities", []):
            if entity.get("type") == "mention":
                mention_text = entity.get("text", "")
                text = text.replace(mention_text, "").strip()

        # Use the Teams conversation ID to maintain context
        conv_id = body.get("conversation", {}).get("id", str(uuid.uuid4()))
        user_name = body.get("from", {}).get("name", "Teams User")

        log.info("Teams message from %s: %s", user_name, text[:100])

        # Run the agent
        from src.coworker.agent import CoworkerAgent
        agent = CoworkerAgent(conversation_id=f"teams-{conv_id}")

        try:
            reply_text = agent.handle_message(text)
        except Exception as exc:
            log.exception("Agent error for Teams message")
            reply_text = f"Sorry, I hit an error: {exc}"

        # Send the reply back to Teams
        await self._send_reply(body, reply_text)

        return Response(status_code=200)

    # ── Send reply to Teams ──────────────────────────────────────────────

    async def _send_reply(self, activity: dict, text: str) -> None:
        token = self._token or await self._get_token()
        service_url = activity.get("serviceUrl", _BOT_API).rstrip("/")

        reply_url = (
            f"{service_url}/v3/conversations/"
            f"{activity['conversation']['id']}/activities/"
            f"{activity['id']}"
        )

        reply_activity = {
            "type": "message",
            "from": activity.get("recipient"),
            "recipient": activity.get("from"),
            "conversation": activity.get("conversation"),
            "text": text,
            "textFormat": "markdown",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                reply_url,
                headers={"Authorization": f"Bearer {token}"},
                json=reply_activity,
            )
            if resp.status_code >= 400:
                log.error("Failed to reply to Teams: %s %s", resp.status_code, resp.text)

    # ── Send proactive alert to a Teams channel ──────────────────────────

    @staticmethod
    async def send_alert_to_webhook(webhook_url: str, title: str, body: str) -> None:
        """
        Send an Adaptive Card to a Teams channel via Incoming Webhook.
        Used by the proactive monitor to push alerts.
        """
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": title,
                                "size": "large",
                                "weight": "bolder",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": body,
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=card)
            if resp.status_code >= 400:
                log.error("Teams webhook failed: %s %s", resp.status_code, resp.text)
