#!/usr/bin/env bash
# Every repository path the agent-facing and user-facing docs cite must resolve.
#
#   bash dev/check_cited_paths.sh [--root DIR] [--allowlist FILE] [--allow-empty] [FILE...]
#
# Adapted from the ci-guards skill's check-agent-paths.sh. Default files (those that exist):
# AGENTS.md, docs/dev/TESTING.md, docs/wiki/*.md and agent-plugin/skills/*/SKILL.md -- the files an
# agent or a user follows literally. tests/test_cited_paths.py runs this over the repository in the
# host suite and drives every rule red from fixture trees.
#
# What it checks:
#   1. A `backticked` single token that looks like a path AND cites this repository: its first
#      segment is a top-level entry of the tree (`tit/...`, `dev/...`, `docs/...`, `loader.sh`), or
#      it is a bare `*.md` document name. It must resolve: relative to the root, relative to the
#      citing file, as a Python module (`tit/calc` is `tit/calc.py`), or as the tail of a tracked
#      file or directory (`tests/e2e/real` is `desktop/tests/e2e/real`). A token with `*`/`?` is a
#      glob and must match something.
#   2. A markdown link target that is not a URL or an anchor must resolve relative to the citing file
#      or the root (strict: that is how a renderer resolves it).
# What it skips, and why: everything else that looks like a path -- `sourcedata/`, `T1w/`,
# `analysis.json`, `derivatives/SimNIBS/...` describe the USER's project, not this tree; URLs,
# `<placeholders>`, `$VAR`, `~/` and absolute paths, tokens with spaces or call/type punctuation;
# paths .gitignore matches (`desktop/out` is build output, described rather than cited).
# Allowlist: the DEFAULT_ALLOWLIST below, or `--allowlist FILE` instead of it. One entry per line:
# `<token-glob>` anywhere, or `<token-glob> <file-glob>` in matching citing files only; `#` comments.
#
# Exit 0 = every cited repository path resolves. Exit 1 = one did not; each is printed as
# `file:line: path does not resolve: token`. Exit 2 = the check could not run: no documents, a named
# document that does not exist, or documents that cite no repository path (`--allow-empty` accepts
# the last one). "Nothing to check" is never reported as "everything resolves".
set -uo pipefail
# Byte-wise pattern classes below: under C, `[!\ -~]` is "any byte outside printable ASCII".
LC_ALL=C
export LC_ALL

# Placeholders and deliberate citations of paths that do not exist. Every entry says why; an entry
# for a stale path names the package that owns the fix, so the entry is deleted with that fix.
DEFAULT_ALLOWLIST='
# Placeholders: a release page per version, an example report module.
*vX.Y.Z*
*/my_report.py
# Cited as deleted: the PyQt5 GUI was removed in v3.0.0 and the docs say so.
tit/gui/*
tit/gui
# Cited as forbidden: dev/documentation_policy.py rejects it.
docs/requirements
# Stale: tit/fields.py was folded into tit/calc.py; the wiki and plugin rewrite
# (feat/calc-envelope-callers) owns the fix and deletes these two entries.
tit/fields
tit/fields.py
'

ROOT="$(pwd)"
ALLOW_EMPTY=0
ALLOW_FILE=""
FILES=()
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$(cd "$2" && pwd)" || exit 2; shift 2 ;;
    --allowlist) ALLOW_FILE="$2"; shift 2 ;;
    --allow-empty) ALLOW_EMPTY=1; shift ;;
    -h|--help) sed -n '2,31p' "$0"; exit 0 ;;
    *) FILES+=("$1"); shift ;;
  esac
done
if [ -n "$ALLOW_FILE" ]; then
  case "$ALLOW_FILE" in /*) ;; *) ALLOW_FILE="$(pwd)/$ALLOW_FILE" ;; esac
  [ -f "$ALLOW_FILE" ] || { echo "check_cited_paths: no allowlist at $ALLOW_FILE" >&2; exit 2; }
fi
cd "$ROOT" || exit 2

if [ ${#FILES[@]} -eq 0 ]; then
  for f in AGENTS.md docs/dev/TESTING.md docs/wiki/*.md agent-plugin/skills/*/SKILL.md; do
    [ -f "$f" ] && FILES+=("$f")
  done
  if [ ${#FILES[@]} -eq 0 ]; then
    echo "check_cited_paths: no documents found under $ROOT -- nothing was checked." >&2
    exit 2
  fi
else
  for f in "${FILES[@]}"; do
    [ -f "$f" ] || { echo "check_cited_paths: $f does not exist -- nothing was checked." >&2; exit 2; }
  done
fi

# The tree, listed once: tracked files in a checkout, otherwise every file but .git/node_modules.
TREE="$(mktemp)"
TOPS="$(mktemp)"
trap 'rm -f "$TREE" "$TOPS"' EXIT
IN_GIT=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IN_GIT=1
  git ls-files > "$TREE"
else
  find . -type f -not -path '*/.git/*' -not -path '*/node_modules/*' | sed 's#^\./##' > "$TREE"
fi
# Top-level entries (directories and root files): a token starting with one cites this repository.
cut -d/ -f1 "$TREE" | sort -u > "$TOPS"

# Does a tracked path end with the file $1, or contain the directory $1 (with or without its `/`)?
tree_has() {
  local t="${1%/}"
  awk -v t="$t" '
    BEGIN { n = length(t); d = t "/" }
    {
      L = length($0)
      if (L >= n && substr($0, L - n + 1) == t && (L == n || substr($0, L - n, 1) == "/")) { f = 1; exit }
      i = index($0, d)
      if (i == 1 || (i > 1 && substr($0, i - 1, 1) == "/")) { f = 1; exit }
    }
    END { exit !f }' "$TREE"
}
ignored() { [ "$IN_GIT" -eq 1 ] && git check-ignore -q -- "$1" 2>/dev/null; }

ALLOW_TOKENS=()
ALLOW_SCOPES=()
read_allowlist() {
  local line tok scope
  while IFS= read -r line; do
    line="${line%%#*}"
    # shellcheck disable=SC2086  # split the entry into its one or two fields
    set -- $line
    [ $# -gt 0 ] || continue
    tok="$1"
    scope="${2:-*}"
    ALLOW_TOKENS+=("$tok")
    ALLOW_SCOPES+=("$scope")
  done
}
if [ -n "$ALLOW_FILE" ]; then
  read_allowlist < "$ALLOW_FILE"
else
  read_allowlist <<< "$DEFAULT_ALLOWLIST"
fi
allowed() { # allowed <file> <token>
  local f="$1" t="$2" i=0
  while [ "$i" -lt ${#ALLOW_TOKENS[@]} ]; do
    # shellcheck disable=SC2053  # the entries are patterns on purpose
    if [[ "$t" == ${ALLOW_TOKENS[$i]} ]] && [[ "$f" == ${ALLOW_SCOPES[$i]} ]]; then
      return 0
    fi
    i=$((i + 1))
  done
  return 1
}

# The token classes that are not paths (see the header). Returns 0 for a candidate.
looks_like_path() {
  local t="$1"
  case "$t" in
    *[!\ -~]*) return 1 ;;
    *' '*|*'<'*|*'>'*|*'('*|*')'*|*'{'*|*'}'*|*'|'*|*'='*|*'@'*|*':'*|*'$'*|*'+'*|*','*|*';'*) return 1 ;;
    /*|'~'*|origin/*|refs/*|-*|.|..) return 1 ;;
    ./*|../*) return 1 ;;
    *[a-z]*) ;;
    *) return 1 ;;
  esac
  case "$t" in
    .*) [[ "$t" == */* ]] || return 1 ;;
  esac
  case "$t" in
    *[\*\?]*) [[ "$t" == */* ]] && return 0; return 1 ;;
    */*) return 0 ;;
    *.md|*.sh|*.mjs|*.cjs|*.js|*.ts|*.tsx|*.py|*.toml|*.yml|*.yaml|*.json|*.cff|*.txt|*.lock) return 0 ;;
  esac
  return 1
}

# Does the token cite this repository (rather than the user's project)? See the header.
cites_repo() {
  local t="$1" first="${1%%/*}"
  [ -n "$first" ] && grep -qxF -- "$first" "$TOPS" && return 0
  case "$t" in
    */*) return 1 ;;
    *.md) return 0 ;;
  esac
  return 1
}

checked=0
failed=0
# check_path <file> <line> <token> <kind>: kind "path" (lenient) or "link" (strict).
check_path() {
  local f="$1" ln="$2" t="$3" kind="$4" dir
  dir="$(dirname "$f")"
  checked=$((checked + 1))
  allowed "$f" "$t" && return 0
  [ -e "$t" ] && return 0
  [ -e "$dir/$t" ] && return 0
  case "$t" in
    *[\*\?]*)
      compgen -G "$t" >/dev/null 2>&1 && return 0
      compgen -G "$dir/$t" >/dev/null 2>&1 && return 0
      echo "$f:$ln: $kind matches nothing: $t" >&2 ;;
    *)
      if [ "$kind" = "path" ]; then
        [ -e "${t%/}.py" ] && return 0
        tree_has "$t" && return 0
        # `desktop/out` is ignored by `out/`, a directory pattern git matches only on `desktop/out/`.
        ignored "$t" && return 0
        ignored "${t%/}/" && return 0
      fi
      echo "$f:$ln: $kind does not resolve: $t" >&2 ;;
  esac
  failed=$((failed + 1))
}

for f in "${FILES[@]}"; do
  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    ln="${hit%%:*}"
    tok="${hit#*:}"
    tok="${tok#\`}"; tok="${tok%\`}"
    tok="${tok%%§*}"
    tok="${tok%%#*}"
    tok="${tok%[,.;]}"
    [ -n "$tok" ] || continue
    looks_like_path "$tok" || continue
    cites_repo "$tok" || continue
    check_path "$f" "$ln" "$tok" "path"
  done < <(grep -on '`[^`]*`' "$f" || true)

  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    ln="${hit%%:*}"
    target="${hit#*:}"
    target="${target#\](}"; target="${target%)}"
    target="${target%% *}"
    target="${target%%#*}"
    case "$target" in ''|http://*|https://*|mailto:*|'<'*|'{'*|*'$'*|/*) continue ;; esac
    check_path "$f" "$ln" "$target" "link"
  done < <(grep -on '\]([^)]*)' "$f" || true)
done

if [ "$checked" -eq 0 ] && [ "$ALLOW_EMPTY" -eq 0 ]; then
  echo "check_cited_paths: ${#FILES[@]} document(s) cite no repository path -- nothing was checked (--allow-empty if that is deliberate)." >&2
  exit 2
fi
if [ "$failed" -gt 0 ]; then
  echo "check_cited_paths: $failed of $checked cited path(s) do not resolve. Fix the document, or allowlist a genuine placeholder in dev/check_cited_paths.sh." >&2
  exit 1
fi
echo "check_cited_paths: ok -- $checked cited path(s) in ${#FILES[@]} document(s) resolve."
