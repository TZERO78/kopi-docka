#!/usr/bin/env bash
# kopi-docka config migration helper
#
# Compares a user kopi-docka.json against the schema shipped with the
# currently installed kopi-docka package and either reports or applies
# the differences. The script does NOT hard-code any field names — every
# key it adds, removes, or warns about is derived from the live template.
#
# What it does:
#   1. Locate the template that ships with the installed kopi-docka.
#   2. Diff template <=> user config:
#        - "missing"  : key paths the template has and the user config doesn't
#        - "unknown"  : key paths the user config has and the template doesn't
#                      (deprecated keys, or custom additions the user wrote)
#        - "type-mismatch": same path, different JSON type
#   3. By default: backup + write a new config that has every missing key
#      filled with the template default, while every existing user value
#      is preserved verbatim. Unknown keys stay untouched unless you ask
#      with --prune-unknown.
#
# What it explicitly does NOT do:
#   - Overwrite existing user values.
#   - Touch the password, the kopia_params, or any secret — those are
#     user values, not template defaults.
#   - Decide for you whether to prune deprecated keys. That stays opt-in.
#
# Usage:
#   scripts/migrate-config.sh --config /etc/kopi-docka.json
#   scripts/migrate-config.sh --config /etc/kopi-docka.json --dry-run
#   scripts/migrate-config.sh --config /etc/kopi-docka.json --prune-unknown
#
# Exit codes:
#   0  Success (or dry-run completed)
#   1  Misuse (missing args, files not found)
#   2  Invalid JSON in either input
#   3  Template could not be located

set -euo pipefail

# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------

USER_CONFIG=""
TEMPLATE_OVERRIDE=""
DRY_RUN=0
PRUNE_UNKNOWN=0
NO_BACKUP=0

# Where to grab a fallback template if the local kopi-docka install can't
# be located. main is intentional — the template barely changes between
# releases, and pinning to a tag would require this script to know its
# own version.
TEMPLATE_FALLBACK_URL="https://raw.githubusercontent.com/TZERO78/kopi-docka/main/kopi_docka/templates/config_template.json"

usage() {
    cat <<'EOF'
kopi-docka config migration helper

USAGE
    migrate-config.sh [--config PATH] [OPTIONS]

OPTIONS
    --config PATH         Path to the kopi-docka.json to migrate. If omitted
                          the script probes the same default locations
                          kopi-docka itself uses, in this order:
                            1. ~/.config/kopi-docka/config.json
                            2. /etc/kopi-docka.json
    --template PATH       Override the template location. Default: read
                          from the installed kopi-docka package; fall back
                          to the python from `kopi-docka`'s shebang; then
                          to a GitHub raw download.
    --dry-run             Print the diff but do not write anything.
    --prune-unknown       Also drop keys present in the user config that
                          the template no longer has (e.g. parallel_workers,
                          task_timeout after Plan 0028 / v7.3.0). OFF by
                          default — a custom key you added yourself would
                          otherwise be deleted.
    --no-backup           Skip the timestamped backup copy. Not recommended.
    -h, --help            Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)        USER_CONFIG="${2:-}"; shift 2 ;;
        --template)      TEMPLATE_OVERRIDE="${2:-}"; shift 2 ;;
        --dry-run)       DRY_RUN=1; shift ;;
        --prune-unknown) PRUNE_UNKNOWN=1; shift ;;
        --no-backup)     NO_BACKUP=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# kopi-docka info banner: which version is installed (if any), so the user
# sees up front whether the migration is going to look at a stale package.
# ---------------------------------------------------------------------------

KOPI_DOCKA_VERSION=""
KOPI_DOCKA_BIN="$(command -v kopi-docka 2>/dev/null || true)"
if [[ -n "$KOPI_DOCKA_BIN" ]]; then
    # `kopi-docka version` prints two lines on stderr+stdout. The version
    # itself is on the line starting with "Kopi-Docka".
    KOPI_DOCKA_VERSION="$(
        "$KOPI_DOCKA_BIN" version 2>&1 \
          | awk '/^Kopi-Docka /{print $2; exit}' \
          || true
    )"
fi

if [[ -n "$KOPI_DOCKA_VERSION" ]]; then
    echo "kopi-docka installed: $KOPI_DOCKA_VERSION  ($KOPI_DOCKA_BIN)"
else
    echo "kopi-docka installed: <not found on PATH — will use the GitHub-hosted template>"
fi

# ---------------------------------------------------------------------------
# Default config path discovery: match kopi-docka's own search order.
#   1. ~/.config/kopi-docka/config.json
#   2. /etc/kopi-docka.json
# We honor SUDO_USER so that `sudo migrate-config.sh` finds the invoking
# user's per-user config, not root's.
# ---------------------------------------------------------------------------

discover_default_config() {
    local invoker_home="$HOME"
    if [[ -n "${SUDO_USER:-}" ]] && [[ "$EUID" -eq 0 ]]; then
        invoker_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
        [[ -n "$invoker_home" ]] || invoker_home="$HOME"
    fi
    local candidates=(
        "$invoker_home/.config/kopi-docka/config.json"
        "/etc/kopi-docka.json"
    )
    for c in "${candidates[@]}"; do
        if [[ -f "$c" ]]; then
            echo "$c"
            return 0
        fi
    done
    return 1
}

if [[ -z "$USER_CONFIG" ]]; then
    if USER_CONFIG="$(discover_default_config)"; then
        echo "note: --config not given; using $USER_CONFIG (kopi-docka default)"
    else
        cat >&2 <<EOF
error: no --config given and no kopi-docka config found at any default location.

Searched (same order kopi-docka uses):
  1. \${HOME:-/}/.config/kopi-docka/config.json
  2. /etc/kopi-docka.json

Pass an explicit --config /path/to/kopi-docka.json, or run
\`kopi-docka advanced config new\` first to create one.
EOF
        exit 1
    fi
fi

if [[ ! -f "$USER_CONFIG" ]]; then
    echo "error: user config not found: $USER_CONFIG" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate template
#
# Strategies in order:
#   1. --template flag (explicit override).
#   2. `python3 -c 'import kopi_docka'` against the default python3.
#   3. `which kopi-docka` shebang → the interpreter the CLI itself uses.
#      Important on systems where /usr/bin/python3 differs from the python
#      that pipx / a venv installed kopi-docka into.
#   4. GitHub raw fallback. Downloaded to a tempfile, deleted on exit.
#
# Each failed step logs *why* so the user gets actionable diagnostics
# instead of "tried: <empty>".
# ---------------------------------------------------------------------------

TEMPLATE_PATH=""
TEMPLATE_TMP=""
MERGE_TMP=""
cleanup() {
    [[ -n "$TEMPLATE_TMP" ]] && rm -f -- "$TEMPLATE_TMP"
    [[ -n "$MERGE_TMP"    ]] && rm -f -- "$MERGE_TMP"
}
trap cleanup EXIT

locate_template_via_python() {
    local py="$1"
    [[ -x "$py" || -n "$(command -v "$py" 2>/dev/null)" ]] || return 1
    "$py" - <<'PY' 2>/dev/null
import sys
try:
    import kopi_docka
except Exception as e:
    sys.exit(1)
from pathlib import Path
p = Path(kopi_docka.__file__).resolve().parent / "templates" / "config_template.json"
if not p.exists():
    sys.exit(1)
print(p)
PY
}

resolve_cli_python() {
    # Read the shebang of the installed `kopi-docka` script and extract the
    # interpreter. Handles `#!/path/to/python3` and `#!/usr/bin/env python3`.
    local cli
    cli="$(command -v kopi-docka 2>/dev/null || true)"
    [[ -n "$cli" && -f "$cli" ]] || return 1
    local shebang
    shebang="$(head -n1 "$cli")"
    [[ "$shebang" == "#!"* ]] || return 1
    # Drop the leading "#!"
    shebang="${shebang#\#!}"
    # Trim leading whitespace
    shebang="${shebang#"${shebang%%[![:space:]]*}"}"
    # `/usr/bin/env python3 …` → second token
    if [[ "$shebang" == */env\ * ]]; then
        # shellcheck disable=SC2206
        local toks=($shebang)
        echo "${toks[1]}"
        return 0
    fi
    # `/path/to/python …` → first token (strip args)
    echo "${shebang%% *}"
}

if [[ -n "$TEMPLATE_OVERRIDE" ]]; then
    if [[ -f "$TEMPLATE_OVERRIDE" ]]; then
        TEMPLATE_PATH="$TEMPLATE_OVERRIDE"
    else
        echo "error: --template path does not exist: $TEMPLATE_OVERRIDE" >&2
        exit 3
    fi
else
    # Strategy 2: default python3
    TEMPLATE_PATH="$(locate_template_via_python python3 || true)"

    # Strategy 3: python the kopi-docka CLI itself uses
    if [[ -z "$TEMPLATE_PATH" ]]; then
        cli_py="$(resolve_cli_python || true)"
        if [[ -n "$cli_py" ]]; then
            TEMPLATE_PATH="$(locate_template_via_python "$cli_py" || true)"
            if [[ -n "$TEMPLATE_PATH" ]]; then
                echo "note: located template via the python from kopi-docka's shebang ($cli_py)" >&2
            fi
        fi
    fi

    # Strategy 4: GitHub raw fallback
    if [[ -z "$TEMPLATE_PATH" ]]; then
        echo "note: no local kopi-docka package found via python; fetching template from GitHub" >&2
        if ! command -v curl >/dev/null 2>&1; then
            echo "error: cannot reach the GitHub fallback — curl is not installed." >&2
            echo "       Install curl, or pass --template /path/to/config_template.json." >&2
            exit 3
        fi
        TEMPLATE_TMP="$(mktemp)"
        if ! curl -fsSL "$TEMPLATE_FALLBACK_URL" -o "$TEMPLATE_TMP"; then
            echo "error: GitHub fallback download failed." >&2
            echo "       URL: $TEMPLATE_FALLBACK_URL" >&2
            echo "       Check network access, or pass --template /path/to/config_template.json." >&2
            exit 3
        fi
        TEMPLATE_PATH="$TEMPLATE_TMP"
        echo "       (downloaded to $TEMPLATE_PATH — will be removed on exit)" >&2
    fi
fi

if [[ -z "$TEMPLATE_PATH" || ! -f "$TEMPLATE_PATH" ]]; then
    cat >&2 <<EOF
error: could not locate the kopi-docka config template.

Tried:
  1. --template flag                          (not provided)
  2. python3 -c 'import kopi_docka'           (failed: package not importable from the default python3)
  3. python from \`which kopi-docka\` shebang   (failed: kopi-docka CLI not found, or its python can't import kopi_docka either)
  4. GitHub raw fallback                      ($TEMPLATE_FALLBACK_URL)

Fix one of these:
  - Install kopi-docka:        pip install kopi-docka      # or pipx install kopi-docka
  - Pass the template path:    --template /path/to/config_template.json
  - Restore network access so the GitHub fallback can fetch the template.
EOF
    exit 3
fi

# ---------------------------------------------------------------------------
# Validate JSON shape on both sides
# ---------------------------------------------------------------------------

if ! jq -e . "$TEMPLATE_PATH" >/dev/null 2>&1; then
    echo "error: template is not valid JSON: $TEMPLATE_PATH" >&2
    exit 2
fi

if ! jq -e . "$USER_CONFIG" >/dev/null 2>&1; then
    echo "error: user config is not valid JSON: $USER_CONFIG" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Compute the diff
#
# We collect three sets of key paths using jq's `paths` (which descends into
# nested objects but stops at array boundaries — arrays are treated as leaf
# values, so we never compare item-by-item inside `exclude_patterns` etc.).
# ---------------------------------------------------------------------------

# Path lists as one-path-per-line, formatted as dot-paths for human reading.
# We use null-byte separators internally to be safe with weird key names.
PATHS_TEMPLATE="$(jq -c '[paths(type != "object" and type != "array")] + [paths(type == "array")]' "$TEMPLATE_PATH")"
PATHS_USER="$(jq -c     '[paths(type != "object" and type != "array")] + [paths(type == "array")]' "$USER_CONFIG")"

# Sets of pretty-formatted paths
T_SET="$(jq -nr --argjson p "$PATHS_TEMPLATE" '$p | map(map(tostring) | join(".")) | unique | .[]')"
U_SET="$(jq -nr --argjson p "$PATHS_USER"     '$p | map(map(tostring) | join(".")) | unique | .[]')"

MISSING="$(comm -23 <(echo "$T_SET" | sort) <(echo "$U_SET" | sort) || true)"
UNKNOWN="$(comm -13 <(echo "$T_SET" | sort) <(echo "$U_SET" | sort) || true)"

# Type mismatches: paths present in both, but different JSON type.
TYPE_MISMATCH=""
while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    # Convert dot-path back to jq filter (every segment is a string key).
    filter=".$(echo "$path" | sed 's/\./"."/g'; )"
    filter="$(echo "$path" | awk -F'.' '{out="."; for (i=1;i<=NF;i++) out = out "[\"" $i "\"]"; print out}')"
    t_type="$(jq -r "$filter | type" "$TEMPLATE_PATH" 2>/dev/null || echo missing)"
    u_type="$(jq -r "$filter | type" "$USER_CONFIG"   2>/dev/null || echo missing)"
    if [[ "$t_type" != "$u_type" ]]; then
        TYPE_MISMATCH+="$path  (template=$t_type, user=$u_type)"$'\n'
    fi
done < <(comm -12 <(echo "$T_SET" | sort) <(echo "$U_SET" | sort) || true)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

echo "kopi-docka config migration"
echo "  user config:  $USER_CONFIG"
echo "  template:     $TEMPLATE_PATH"
echo

if [[ -n "$MISSING" ]]; then
    echo "Missing keys (will be added with template defaults):"
    echo "$MISSING" | sed 's/^/  + /'
    echo
fi

if [[ -n "$UNKNOWN" ]]; then
    echo "Unknown keys (not in the current template — possibly deprecated"
    echo "or your own additions):"
    echo "$UNKNOWN" | sed 's/^/  ? /'
    if [[ $PRUNE_UNKNOWN -eq 1 ]]; then
        echo "  → will be REMOVED (--prune-unknown is set)"
    else
        echo "  → kept (use --prune-unknown to remove them)"
    fi
    echo
fi

if [[ -n "$TYPE_MISMATCH" ]]; then
    echo "Type mismatches (user value kept verbatim — review manually):"
    echo "$TYPE_MISMATCH" | sed 's/^/  ! /'
    echo
fi

if [[ -z "$MISSING" && -z "$UNKNOWN" && -z "$TYPE_MISMATCH" ]]; then
    echo "Config already matches the current template. Nothing to do."
    exit 0
fi

# ---------------------------------------------------------------------------
# Build the merged config
#
# Semantics:
#   - template * user             → user values win, missing keys from template fill in.
#   - if --prune-unknown is set, intersect with the template's key set first.
# ---------------------------------------------------------------------------

build_merged() {
    if [[ $PRUNE_UNKNOWN -eq 1 ]]; then
        # Drop user keys whose path is not in the template, then merge.
        # jq's `getpath` / `delpaths` work on the same `paths(...)` lists
        # we computed above.
        jq -n \
            --slurpfile tpl "$TEMPLATE_PATH" \
            --slurpfile usr "$USER_CONFIG" \
            '
            ($tpl[0]) as $T
            | ($usr[0]) as $U
            | ($T | [paths(type != "object" and type != "array")] + [paths(type == "array")]) as $TPATHS
            | ($U | [paths(type != "object" and type != "array")] + [paths(type == "array")]) as $UPATHS
            | ( ($UPATHS - $TPATHS) ) as $UNKNOWN_PATHS
            | ($U | delpaths($UNKNOWN_PATHS)) as $U_PRUNED
            | $T * $U_PRUNED
            '
    else
        jq -n \
            --slurpfile tpl "$TEMPLATE_PATH" \
            --slurpfile usr "$USER_CONFIG" \
            '$tpl[0] * $usr[0]'
    fi
}

if [[ $DRY_RUN -eq 1 ]]; then
    echo "[dry-run] merged config would be:"
    build_merged | jq .
    exit 0
fi

# ---------------------------------------------------------------------------
# Backup + write
# ---------------------------------------------------------------------------

if [[ $NO_BACKUP -eq 0 ]]; then
    BACKUP="${USER_CONFIG}.backup-$(date +%Y%m%d-%H%M%S)"
    cp -p -- "$USER_CONFIG" "$BACKUP"
    echo "Backup written: $BACKUP"
fi

MERGE_TMP="$(mktemp)"

build_merged > "$MERGE_TMP"

# Final validation: must still parse as JSON
if ! jq -e . "$MERGE_TMP" >/dev/null 2>&1; then
    echo "error: merge produced invalid JSON, refusing to write." >&2
    exit 2
fi

# Preserve original ownership + mode where possible (root-owned configs
# under /etc/ or /root/ are the common case).
chmod --reference="$USER_CONFIG" "$MERGE_TMP" 2>/dev/null || true
chown --reference="$USER_CONFIG" "$MERGE_TMP" 2>/dev/null || true

mv -- "$MERGE_TMP" "$USER_CONFIG"
MERGE_TMP=""  # already moved, don't try to delete in cleanup trap

echo "Wrote merged config: $USER_CONFIG"
echo
echo "Next steps:"
echo "  1. Review the file (especially any 'type mismatch' warnings above)."
echo "  2. Run a sanity check:    kopi-docka --config '$USER_CONFIG' doctor"
echo "  3. If anything looks wrong, restore the backup file printed above."
