# vault-audit

A fast, dependency-free health check for [Obsidian](https://obsidian.md) vaults.

One command tells you what quietly rotted since you last looked: broken links,
notes nobody linked, missing frontmatter, and duplicates you forgot you made.

```console
$ python3 vault_audit.py ~/Documents/Obsidian\ Vault
vault-audit 1.1.0
Vault: /Users/you/Documents/Obsidian Vault
Notes: 159

[1] Wikilinks: 578 total, 0 broken

[2] Without frontmatter: 0

[3] Orphans (nothing links to them): 3
    README.md
    LIESMICH.md
    _Testbranch/00 — README.md

[4] Byte-identical notes: 0 group(s)
    Near-identical (>55%): 0  [214 pairs compared in full]

Runtime: 4.7 s
```

## Why another link checker

Most of them report links that are not broken.

macOS stores filenames **decomposed** (NFD) while Obsidian writes links
**composed** (NFC). `Résumé draft` in a filename and `Résumé draft` in a
`[[wikilink]]` are then different byte strings. A naive comparison flags every
accented link as broken and every accented note as an orphan.

On a real 114-note vault that meant **136 false positives out of 137 findings.**
The actual count was one — and that one turned out to be a link inside a fenced
code block, i.e. an example, not a reference.

`vault-audit` normalises both sides before comparing, and ignores links inside
` ``` ` fences and `inline code`. What it reports is what is actually wrong.

## Install

There is nothing to install. One file, Python 3.8+, no third-party packages.

```bash
curl -O https://raw.githubusercontent.com/julianangst/vault-audit/main/vault_audit.py
python3 vault_audit.py
```

## Usage

```bash
python3 vault_audit.py                              # ~/Documents/Obsidian Vault
python3 vault_audit.py /path/to/vault
python3 vault_audit.py /path/to/vault --json
python3 vault_audit.py /path/to/vault --fail-on broken-links --fail-on duplicates
```

| Flag | Effect |
|---|---|
| `--json` | machine-readable output, same data |
| `--fail-on CATEGORY` | exit `1` when that category has findings — repeatable |
| `--version` | print the version |

Categories for `--fail-on`: `broken-links`, `missing-frontmatter`, `orphans`,
`duplicates`.

| Exit code | Meaning |
|---:|---|
| `0` | clean, or nothing selected by `--fail-on` |
| `1` | findings in a selected category |
| `2` | the path is not a directory |

## What it checks

**1 — Broken wikilinks.** Unicode-normalised, trailing table escapes stripped,
code blocks excluded. Handles `[[note|alias]]`, `[[note#heading]]` and
`[[note^block]]`.

**2 — Missing frontmatter.** A YAML block counts only when it is opened *and*
closed. A note starting with a bare `---` horizontal rule is not frontmattered,
and most checkers get that wrong.

**3 — Orphans.** Notes nothing links to. Entry points such as `README` are
expected to show up here — the list is a prompt, not a verdict.

**4 — Duplicates.** Byte-identical notes, plus near-identical ones above 55%
similarity.

## Speed

The duplicate check is quadratic by nature. A word-set prefilter runs before the
expensive comparison, so only genuinely similar candidates get compared in full.

| Vault size | Without prefilter | With prefilter |
|---:|---:|---:|
| 114 notes | 18.5 s | **4.8 s** |
| 400 notes | 74.5 s | **40.4 s** |

Measured on an M-series Mac. Your numbers will differ; the ratio should not.

## Continuous checking

If your vault lives in git, `.github/workflows/vault-audit.yml` in this repo
fails the build when a broken link lands on the main branch:

```yaml
- run: python3 vault_audit.py . --fail-on broken-links
```

## Ignored by default

`node_modules`, `.obsidian`, `.git`, `.trash`, `.stfolder`, `.wwebjs_auth`,
`.wwebjs_cache`, `_to_delete`, `__pycache__`, and every other dot-directory.

If your vault has `node_modules` in it, that alone is worth a look — Obsidian
indexes every file it finds, and a single dependency tree can be ten thousand of
them.

## What it does not do

It does not change your files. It reads, counts and reports. Fixing is a
separate decision, and one a script should not make on its own.

## Example

[`examples/report-example.txt`](examples/report-example.txt) is real output from
the small demo vault used in the tests — including the accented-filename case
that trips up naive checkers.

## License

MIT — see [LICENSE](LICENSE).
