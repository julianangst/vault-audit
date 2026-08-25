"""Tests for vault-audit. Run with: python3 tests/test_vault_audit.py"""
import os
import shutil
import sys
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vault_audit import audit  # noqa: E402

FAILURES = []


def check(name, got, want):
    if got == want:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}: got {got!r}, want {want!r}")
        FAILURES.append(name)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    root = tempfile.mkdtemp()
    try:
        # an accented filename stored the way macOS stores it
        accented = unicodedata.normalize("NFD", "Résumé.md")
        write(root, accented, "---\ntitle: r\n---\nbody\n")
        write(root, "Home.md", "---\ntitle: h\n---\n[[Résumé]] and [[Nowhere]]\n")
        write(root, "Code.md", "---\ntitle: c\n---\n```\n[[Only an example]]\n```\n")
        write(root, "Rule.md", "---\n\nA horizontal rule, not frontmatter.\n")
        write(root, "A.md", "---\ntitle: a\n---\nsame body\n")
        write(root, "B.md", "---\ntitle: a\n---\nsame body\n")
        write(root, "node_modules/x/README.md", "ignored\n")

        r = audit(root)

        check("accented link resolves", [b["target"] for b in r["broken_links"]], ["Nowhere"])
        check("code block ignored", r["links_total"], 2)
        check("bare rule is not frontmatter", "Rule.md" in r["missing_frontmatter"], True)
        check("node_modules skipped", r["notes"], 6)
        check("identical pair found", len(r["identical"]), 1)
        check("orphans listed", "Code.md" in r["orphans"], True)
        check("clean vault has no crash", audit(tempfile.mkdtemp())["notes"], 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} test(s) failed.")
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
