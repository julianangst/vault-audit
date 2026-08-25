#!/usr/bin/env python3
"""
vault-audit — a fast, dependency-free health check for Obsidian vaults.

Finds four things that quietly rot a vault:

  1. broken wikilinks   (Unicode-normalised, code blocks excluded)
  2. notes without YAML frontmatter
  3. orphans — notes nothing links to
  4. duplicates — byte-identical and near-identical notes

Usage
    python3 vault_audit.py                       # ~/Documents/Obsidian Vault
    python3 vault_audit.py /path/to/vault
    python3 vault_audit.py /path/to/vault --json
    python3 vault_audit.py /path/to/vault --fail-on broken-links

Exit codes
    0  clean (or nothing selected by --fail-on)
    1  findings in a category named by --fail-on
    2  the path is not a directory

No third-party packages. Python 3.8+.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import sys
import time
import unicodedata as ud
from difflib import SequenceMatcher

__version__ = "1.1.0"

SKIP_DIRS = {
    "node_modules", ".obsidian", ".git", ".trash", ".stfolder",
    ".wwebjs_auth", ".wwebjs_cache", "_to_delete", "__pycache__",
}
SIMILAR_AT = 0.55      # ratio above which two notes count as near-duplicates
PREFILTER_AT = 0.30    # word-set overlap required before the expensive compare

CODE_BLOCK = re.compile(r"^```.*?^```", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")
WIKILINK = re.compile(r"\[\[([^\]\n]+)\]\]")
WORD = re.compile(r"[0-9a-zA-ZäöüÄÖÜßàâçéèêëîïôûùüÿñæœ]{4,}")


def nfc(text: str) -> str:
    """Normalise for comparison.

    macOS stores filenames decomposed (NFD) while Obsidian writes links
    composed (NFC). Without this, 'für' in a filename and 'für' in a link are
    different byte strings and every accented link looks broken.
    """
    return ud.normalize("NFC", text).strip().rstrip("\\").strip()


def strip_code(text: str) -> str:
    """Links inside code fences are examples, not references."""
    return INLINE_CODE.sub(" ", CODE_BLOCK.sub(" ", text))


def has_frontmatter(text: str) -> bool:
    """True only when the YAML block is opened *and* closed."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    return any(line.strip() in ("---", "...") for line in lines[1:60])


def word_set(text: str) -> set:
    return {w.lower() for w in WORD.findall(text)}


def load(root: str):
    notes, unreadable = {}, []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    notes[path] = fh.read()
            except OSError as err:
                unreadable.append((path, err.strerror))
    return notes, unreadable


def audit(root: str) -> dict:
    started = time.time()
    notes, unreadable = load(root)
    rel = lambda p: os.path.relpath(p, root)

    result = {
        "vault": root,
        "version": __version__,
        "notes": len(notes),
        "unreadable": [{"file": rel(p), "reason": r} for p, r in unreadable],
        "links_total": 0,
        "broken_links": [],
        "missing_frontmatter": [],
        "orphans": [],
        "identical": [],
        "similar": [],
        "pairs_compared": 0,
        "seconds": 0.0,
    }
    if not notes:
        result["seconds"] = round(time.time() - started, 2)
        return result

    stems = {nfc(os.path.splitext(os.path.basename(p))[0]): p for p in notes}
    cleaned = {p: strip_code(t) for p, t in notes.items()}

    linked = set()
    broken = set()
    for path, text in cleaned.items():
        for raw in WIKILINK.findall(text):
            target = nfc(raw.split("|")[0].split("#")[0].split("^")[0])
            result["links_total"] += 1
            if not target:
                continue
            linked.add(target)
            if target not in stems:
                broken.add((rel(path), target))
    result["broken_links"] = [{"file": f, "target": t} for f, t in sorted(broken)]

    result["missing_frontmatter"] = sorted(
        rel(p) for p, t in notes.items() if not has_frontmatter(t)
    )
    result["orphans"] = sorted(rel(p) for s, p in stems.items() if s not in linked)

    buckets = {}
    for path, text in notes.items():
        buckets.setdefault(hashlib.md5(nfc(text).encode()).hexdigest(), []).append(rel(path))
    result["identical"] = [group for group in buckets.values() if len(group) > 1]

    items = [(rel(p), nfc(t), word_set(t)) for p, t in notes.items()]
    for (p1, t1, w1), (p2, t2, w2) in itertools.combinations(items, 2):
        if not w1 or not w2:
            continue
        small, large = (w1, w2) if len(w1) <= len(w2) else (w2, w1)
        if len(small) / len(large) < PREFILTER_AT:
            continue
        if len(small & large) / len(small) < PREFILTER_AT:
            continue
        result["pairs_compared"] += 1
        ratio = SequenceMatcher(None, t1, t2).ratio()
        if ratio > SIMILAR_AT:
            result["similar"].append({"ratio": round(ratio, 3), "a": p1, "b": p2})
    result["similar"].sort(key=lambda x: -x["ratio"])

    result["seconds"] = round(time.time() - started, 2)
    return result


def render(r: dict) -> str:
    out = [f"vault-audit {r['version']}", f"Vault: {r['vault']}", f"Notes: {r['notes']}", ""]
    if r["unreadable"]:
        out.append(f"[!] {len(r['unreadable'])} file(s) could not be read")
        out += [f"    {u['file']} — {u['reason']}" for u in r["unreadable"]]
        out.append("")
    if not r["notes"]:
        out.append("No notes found — nothing to check.")
        return "\n".join(out)

    out.append(f"[1] Wikilinks: {r['links_total']} total, {len(r['broken_links'])} broken")
    out += [f"    {b['file']}  ->  [[{b['target']}]]" for b in r["broken_links"]]

    out.append("")
    out.append(f"[2] Without frontmatter: {len(r['missing_frontmatter'])}")
    out += [f"    {f}" for f in r["missing_frontmatter"]]

    out.append("")
    out.append(f"[3] Orphans (nothing links to them): {len(r['orphans'])}")
    out += [f"    {f}" for f in r["orphans"]]

    out.append("")
    out.append(f"[4] Byte-identical notes: {len(r['identical'])} group(s)")
    out += [f"    {g}" for g in r["identical"]]
    out.append(
        f"    Near-identical (>{int(SIMILAR_AT * 100)}%): {len(r['similar'])}"
        f"  [{r['pairs_compared']} pairs compared in full]"
    )
    out += [f"    {s['ratio']}  {s['a']}  <->  {s['b']}" for s in r["similar"][:20]]

    out.append("")
    out.append(f"Runtime: {r['seconds']} s")
    return "\n".join(out)


FAIL_KEYS = {
    "broken-links": "broken_links",
    "missing-frontmatter": "missing_frontmatter",
    "orphans": "orphans",
    "duplicates": "identical",
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="vault-audit",
        description="Health check for Obsidian vaults. No dependencies.",
    )
    parser.add_argument("vault", nargs="?", default="~/Documents/Obsidian Vault",
                        help="path to the vault (default: ~/Documents/Obsidian Vault)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--fail-on", choices=sorted(FAIL_KEYS), action="append", default=[],
                        metavar="CATEGORY",
                        help="exit 1 when this category has findings; repeatable")
    parser.add_argument("--version", action="version", version=f"vault-audit {__version__}")
    args = parser.parse_args(argv)

    root = os.path.abspath(os.path.expanduser(args.vault))
    if not os.path.isdir(root):
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    result = audit(root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))

    for choice in args.fail_on:
        if result[FAIL_KEYS[choice]]:
            print(f"\nFailing: {choice} has findings.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
