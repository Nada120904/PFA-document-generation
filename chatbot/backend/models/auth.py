"""Authentication models for the chatbot backend."""

from pydantic import BaseModel


class SignUpRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    name: str
    email: str
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    user_id: str
    name: str
    email: str
