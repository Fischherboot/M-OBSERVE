import bcrypt
import secrets
import random

WORDS = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
    "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey",
    "xray", "yankee", "zulu", "phoenix", "shadow", "cyber", "nexus",
    "pulse", "orbit", "solar", "lunar", "titan", "spark", "blaze", "frost",
    "storm", "surge", "comet", "nova", "viper", "cobra", "raven", "falcon",
    "eagle", "ghost", "helix", "prism"
]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def generate_api_key() -> str:
    word = random.choice(WORDS)
    digits = random.randint(1000, 9999)
    return f"observe-{word}-{digits}"


def generate_action_token() -> str:
    return secrets.token_hex(16)
