# ASCII face library for agent personas.
# WHY: Terminal-native "avatars" — no image rendering needed.
# Each face has a key, a display name, and an art block (rendered in Rich panels).
# Faces are deliberately distinct so a lawyer can visually recognise which agent they're using.

from __future__ import annotations

FACES: dict[str, dict] = {
    "sharp_counsel": {
        "name": "Sharp Counsel",
        "description": "Focused. Aggressive. Always winning.",
        "art": r"""
   ___
  /o o\
  | ‾ |
  | ═ |
 /|   |\
""",
    },
    "calm_negotiator": {
        "name": "Calm Negotiator",
        "description": "Measured. Strategic. Finds the settlement.",
        "art": r"""
   ___
  /~ ~\
  | ‿ |
  | — |
 /|   |\
""",
    },
    "senior_silk": {
        "name": "Senior Silk",
        "description": "Veteran. Gravitas. Commands the courtroom.",
        "art": r"""
  _____
 /∞   ∞\
 |  ω  |
 |  ═  |
/|     |\
""",
    },
    "tech_lawyer": {
        "name": "Tech Lawyer",
        "description": "Digital-first. IP/data law. Codes and argues.",
        "art": r"""
  ┌───┐
  │◉ ◉│
  │ ▾ │
  │ ≡ │
  └───┘
""",
    },
    "constitutional": {
        "name": "The Constitutionalist",
        "description": "Article-by-article. Fundamental rights are everything.",
        "art": r"""
   ___
  (⊙ ⊙)
  ( ▵ )
  [ ═ ]
 /[   ]\
""",
    },
    "deal_maker": {
        "name": "Deal Maker",
        "description": "Transactional. Commercial. Closes the deal.",
        "art": r"""
   ___
  /◕ ◕\
  | ∪ |
  | ▬ |
 /|   |\
""",
    },
    "fierce_hawk": {
        "name": "Fierce Hawk",
        "description": "Zero tolerance. Criminal defence at its sharpest.",
        "art": r"""
  _____
 />   <\
 | > < |
 |  ▀  |
/|     |\
""",
    },
    "wise_owl": {
        "name": "Wise Owl",
        "description": "Scholarly. Research-heavy. Never misses a citation.",
        "art": r"""
  /\_/\
 ( o.o )
  > ⌒ <
  |   |
  |___|
""",
    },
}

FACE_KEYS = list(FACES.keys())


def get_face(key: str) -> dict:
    return FACES.get(key, FACES["sharp_counsel"])


def render_face(key: str) -> str:
    """Return a Rich-compatible string with the face art."""
    face = get_face(key)
    return f"[bold cyan]{face['art']}[/bold cyan]"


def list_faces_table() -> list[dict]:
    """Return a list of face summaries for selection menus."""
    return [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in FACES.items()
    ]
