"""User and auth payloads."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Languages offered in the UI. The coaching brain accepts any language string;
# this list only drives the picker.
SUPPORTED_LANGUAGES: list[str] = [
    "English", "Tamil", "Hindi", "Telugu", "Kannada", "Malayalam", "Bengali", "Marathi",
    "Spanish", "Portuguese", "French", "German", "Italian", "Russian", "Arabic",
    "Mandarin Chinese", "Japanese", "Korean", "Turkish", "Vietnamese", "Indonesian",
]


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    preferred_language: str = Field(default="English", max_length=32)
    goal: str = Field(default="", max_length=500)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    preferred_language: str | None = Field(default=None, max_length=32)
    goal: str | None = Field(default=None, max_length=500)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    preferred_language: str
    current_rating_estimate: int
    goal: str
    assessment_completed: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
