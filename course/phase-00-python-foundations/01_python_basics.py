"""
01 — Python Basics
==================
If you already code Python daily, skim this and move to 02.
If Python is new-ish or you want to be sure you know the foundations,
read every section carefully. The ideas here appear constantly in LexAgent.

Run this file:
    python 01_python_basics.py
"""

# ──────────────────────────────────────────────
# SECTION 1: Variables and built-in types
# ──────────────────────────────────────────────
# Python has no type declarations by default — you just assign a value.
# The type is inferred from the value on the right side.

name = "Brahm"           # str
matter_count = 42        # int
is_verified = True       # bool
fee_amount = 12500.50    # float
parties = ["ABC Ltd", "XYZ Developers"]   # list
matter = {"type": "writ", "court": "HC"}  # dict
nothing = None           # NoneType — the "no value" value

print("=== SECTION 1: Built-in types ===")
print(f"name is a {type(name).__name__}: {name}")
print(f"parties is a {type(parties).__name__}: {parties}")
print(f"matter is a {type(matter).__name__}: {matter}")
print(f"nothing is a {type(nothing).__name__}: {nothing}")


# ──────────────────────────────────────────────
# SECTION 2: Functions
# ──────────────────────────────────────────────
# A function is a reusable block of logic. You define it with `def`.
# You call it by name with parentheses.

def format_matter_id(matter_id: str) -> str:
    """
    Return a display-friendly version of a matter ID.
    The stuff in triple quotes is a docstring — it documents what the function does.
    """
    return f"Matter #{matter_id.upper()}"

result = format_matter_id("m-20240501-001")
print("\n=== SECTION 2: Functions ===")
print(result)   # Matter #M-20240501-001

# Functions can have default arguments.
def greet_lawyer(name: str, title: str = "Advocate") -> str:
    return f"Good morning, {title} {name}."

print(greet_lawyer("Sharma"))              # uses default title
print(greet_lawyer("Mehta", "Senior Adv")) # overrides title


# ──────────────────────────────────────────────
# SECTION 3: Optional values and None checks
# ──────────────────────────────────────────────
# In LexAgent, almost every field in LexState is Optional — meaning it can be None.
# You will see this pattern constantly: check before using.

def display_jurisdiction(jurisdiction: str | None) -> str:
    # `str | None` means "either a string or None" — Python 3.10+ syntax.
    # The older spelling is `Optional[str]` from the typing module.
    if jurisdiction is None:
        return "(jurisdiction not set)"
    return jurisdiction

print("\n=== SECTION 3: Optional values ===")
print(display_jurisdiction("Delhi High Court"))
print(display_jurisdiction(None))


# ──────────────────────────────────────────────
# SECTION 4: Lists and dicts — the workhorses
# ──────────────────────────────────────────────
# research_findings in LexState is a list of dicts.
# Each dict has keys like case_name, citation, relevance, url, source.

findings = [
    {"case_name": "Kesavananda Bharati v State of Kerala",
     "citation": "AIR 1973 SC 1461",
     "relevance": "foundational constitutional case"},
    {"case_name": "Maneka Gandhi v Union of India",
     "citation": "AIR 1978 SC 597",
     "relevance": "personal liberty under Article 21"},
]

# Access a dict value by key
first_case = findings[0]["case_name"]
print("\n=== SECTION 4: Lists and dicts ===")
print(f"First case: {first_case}")

# Loop over a list
for f in findings:
    print(f"  → {f['citation']}: {f['case_name']}")

# .get() is safer than [] when a key might not exist
url = findings[0].get("url", "no URL")
print(f"URL: {url}")   # no URL — the key doesn't exist


# ──────────────────────────────────────────────
# SECTION 5: List comprehensions
# ──────────────────────────────────────────────
# LexAgent uses these to transform lists in one line.
# Pattern: [expression for item in iterable if condition]

citations = [f["citation"] for f in findings]
print("\n=== SECTION 5: List comprehensions ===")
print("All citations:", citations)

# With a filter: only cases with "SC" in the citation
sc_citations = [f["citation"] for f in findings if "SC" in f["citation"]]
print("Supreme Court citations:", sc_citations)


# ──────────────────────────────────────────────
# SECTION 6: Importing modules
# ──────────────────────────────────────────────
# Python code is organized into modules (files) and packages (folders with __init__.py).
# You import what you need with `import` or `from ... import`.

import os          # built-in — operating system utilities
from pathlib import Path  # built-in — file paths done right

# Path() is much better than string concatenation for file paths.
home = Path.home()
lexagent_home = home / ".lexagent"   # works on Mac, Windows, Linux
print("\n=== SECTION 6: Imports and Path ===")
print(f"Home dir: {home}")
print(f"LexAgent home would be: {lexagent_home}")

# os.environ is a dict of environment variables
# (we'll go deep on this in 05_env_files.py)
current_dir = os.getcwd()
print(f"Current directory: {current_dir}")


# ──────────────────────────────────────────────
# SECTION 7: Exception handling
# ──────────────────────────────────────────────
# Every LexAgent node has the same error pattern:
#   try:
#       ... do work ...
#       return {"result": value}
#   except Exception as e:
#       return {"error": str(e)}
#
# Nodes NEVER raise. They catch everything and return {"error": ...}.
# This lets the graph continue even when one node fails.

def safe_divide(a: float, b: float) -> dict:
    try:
        return {"result": a / b, "error": None}
    except ZeroDivisionError as e:
        return {"result": None, "error": str(e)}

print("\n=== SECTION 7: Exception handling ===")
print(safe_divide(10, 2))    # {"result": 5.0, "error": None}
print(safe_divide(10, 0))    # {"result": None, "error": "division by zero"}


# ──────────────────────────────────────────────
# SECTION 8: f-strings and string formatting
# ──────────────────────────────────────────────
# f-strings (formatted string literals) are used everywhere in LexAgent.

lawyer_name = "Adv. Sharma"
matter_type = "Writ Petition"
court = "Delhi High Court"

prompt_fragment = f"""
You are a legal assistant for {lawyer_name}.
Draft a {matter_type} for filing before the {court}.
"""
print("\n=== SECTION 8: f-strings ===")
print(prompt_fragment)


# ──────────────────────────────────────────────
# PAUSE AND THINK
# ──────────────────────────────────────────────
# Before moving to 02_type_hints_typeddict.py, make sure you can answer:
#
# 1. What is the difference between [] and .get() when accessing a dict?
# 2. What does `str | None` mean in a function signature?
# 3. Why do LexAgent nodes return {"error": str(e)} instead of raising?
# 4. What does Path.home() / ".lexagent" do?
#
# If you cannot answer all four, re-read the relevant sections above.
# If you can, move on.

print("\n=== DONE — move on to 02_type_hints_typeddict.py ===")
