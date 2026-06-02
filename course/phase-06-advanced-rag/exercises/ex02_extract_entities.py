"""
Phase 6 — Exercise 2: Extract Legal Entities Using Regex

Implement 3 extractors using only the re module (no LLM needed).
"""
import re

SAMPLE_JUDGMENT = (
    "In Maneka Gandhi v. Union of India, decided in 1978, the Supreme Court "
    "of India overruled A.K. Gopalan v. State of Madras (1950) and held that "
    "Article 21, read with Article 14 and Article 19, guarantees a cluster of "
    "fundamental rights. Section 10 of the Passports Act, 1967, under which the "
    "passport was impounded, was found to violate the right to natural justice. "
    "The judgment was followed in Francis Coralie v. Union Territory Delhi in 1981 "
    "and Olga Tellis v. Bombay Municipal Corporation in 1985."
)


def extract_case_names(text: str) -> list[str]:
    """
    Extract case names matching 'Word(s) v. Word(s)' or 'Word(s) v Word(s)' patterns.

    Examples to match:
        "Maneka Gandhi v. Union of India"
        "A.K. Gopalan v. State of Madras"
        "Francis Coralie v. Union Territory Delhi"

    Tips:
        - Pattern starts with an uppercase word (may include '.')
        - Followed by one or more words
        - Then ' v. ' or ' v '
        - Then one or more words

    Returns: deduplicated list, preserving first-occurrence order.
    """
    # TODO: implement using re.findall()
    # Suggested pattern: r'[A-Z][A-Za-z.]+(?:\s+[A-Za-z.]+)*\s+v\.?\s+[A-Z][A-Za-z\s]+'
    pass


def extract_section_numbers(text: str) -> list[str]:
    """
    Extract 'Section N' or 'Article N' references.

    Examples to match:
        "Article 21"
        "Article 14"
        "Section 10"
        "Section 138"

    Returns: deduplicated list.
    """
    # TODO: implement using re.findall()
    # Pattern: r'(?:Article|Section)\s+\d+[A-Z]?'
    pass


def extract_years(text: str) -> list[str]:
    """
    Extract 4-digit years in the range 1947–2025 (post-independence Indian law).

    Examples: "1978", "1950", "1985", "1967"

    Returns: deduplicated list, preserving order.
    """
    # TODO: implement — pattern should match 19[4-9]\d or 20[0-2]\d
    pass


def extract_all(text: str) -> dict:
    """
    Run all 3 extractors. Return combined dict.
    """
    # TODO: return {"cases": [...], "sections": [...], "years": [...]}
    pass


# ── TESTS ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = extract_all(SAMPLE_JUDGMENT)

    assert result is not None, "extract_all returned None"
    assert "cases" in result and "sections" in result and "years" in result

    print("── Extracted Entities ──")
    print(f"Cases ({len(result['cases'])}):")
    for c in result["cases"]:
        print(f"  - {c}")

    print(f"\nSections/Articles ({len(result['sections'])}):")
    for s in result["sections"]:
        print(f"  - {s}")

    print(f"\nYears ({len(result['years'])}):")
    for y in result["years"]:
        print(f"  - {y}")

    # Assertions
    assert any("Maneka" in c for c in result["cases"]), "Should find Maneka Gandhi case"
    print("\n✓ Found Maneka Gandhi case")

    assert any("21" in s for s in result["sections"]), "Should find Article 21"
    print("✓ Found Article 21")

    assert "1978" in result["years"], "Should find year 1978"
    assert "2030" not in result["years"], "Should not find future year 2030"
    print("✓ Year extraction correct")

    assert len(result["cases"]) == len(set(result["cases"])), "Cases should be deduplicated"
    print("✓ No duplicate cases")

    print("\n✅ All tests passed!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/tools/legal_kg.py — does it use regex extraction or LLM extraction?
#    What can an LLM extract that regex cannot? Give a concrete example.
# 2. "A.K. Gopalan" has a period in the name — does your regex handle this correctly?
#    Test with: "A.K. Gopalan v. State of Madras"
# 3. The SAMPLE_JUDGMENT has "Passports Act, 1967" — does your Section extractor
#    catch "Section 10 of the Passports Act"? If not, how would you fix the pattern?
