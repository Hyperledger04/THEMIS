"""
build_skill.py — compile a skill directory into a distributable .skill ZIP.

Usage:
    python -m themis.skills.build_skill themis/skills/indian_doc_formatter
    python -m themis.skills.build_skill themis/skills/indian_doc_formatter --out dist/

A .skill file is a ZIP archive with this layout:
    manifest.yaml       — required; YAML metadata
    SKILL.md            — required; main instruction body
    references/*.md     — optional; style profiles, checklists, etc.
    learnings.md        — optional; accumulated rules

WHY a separate build step instead of just reading directories at runtime:
  Runtime directory reading (also supported) works fine for local development.
  The .skill format exists for *distribution* — share one file, install with
  `cp my_skill.skill ~/.themis/skills/`, no directory structure to preserve.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def build(source_dir: Path, out_dir: Path) -> Path:
    """
    Package source_dir into a .skill ZIP in out_dir.
    Returns the path of the created .skill file.
    Raises FileNotFoundError if manifest.yaml or SKILL.md are missing.
    """
    manifest = source_dir / "manifest.yaml"
    skill_md = source_dir / "SKILL.md"

    if not manifest.exists():
        raise FileNotFoundError(f"manifest.yaml not found in {source_dir}")
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found in {source_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{source_dir.name}.skill"

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest, "manifest.yaml")
        zf.write(skill_md, "SKILL.md")

        refs_dir = source_dir / "references"
        if refs_dir.is_dir():
            for ref in sorted(refs_dir.glob("*.md")):
                zf.write(ref, f"references/{ref.name}")

        learnings = source_dir / "learnings.md"
        if learnings.exists():
            zf.write(learnings, "learnings.md")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package a skill directory into a .skill ZIP for distribution.",
    )
    parser.add_argument("source", help="Path to the skill source directory")
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory (default: same as source's parent)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source).resolve()
    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out).resolve() if args.out else source_dir.parent
    output_path = build(source_dir, out_dir)
    print(f"Built: {output_path}")


if __name__ == "__main__":
    main()
