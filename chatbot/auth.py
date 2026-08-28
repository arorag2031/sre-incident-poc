import json
from pathlib import Path

USERS_FILE = Path(__file__).resolve().parent / "users.json"


def load_users():
    with USERS_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def authenticate(email: str, password: str):
    email_norm = (email or "").strip().lower()
    for user in load_users():
        if user.get("email", "").strip().lower() == email_norm and user.get("password") == password:
            return {"email": user["email"], "name": user.get("name") or user["email"]}
    return None
