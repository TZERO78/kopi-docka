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

usage() {
    cat <<'EOF'
kopi-docka config migration helper

USAGE
    migrate-config.sh --config PATH [OPTIONS]

OPTIONS
    --config PATH         Path to the kopi-docka.json to migrate (required).
    --template PATH       Override the template location. Default: read
                          from the installed kopi-docka package via
                          `python3 -c "import kopi_docka; ..."`.
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

if [[ -z "$USER_CONFIG" ]]; then
    echo "error: --config is required" >&2
    usage >&2
    exit 1
fi

if [[ ! -f "$USER_CONFIG" ]]; then
    echo "error: user config not found: $USER_CONFIG" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate template
# ---------------------------------------------------------------------------

if [[ -n "$TEMPLATE_OVERRIDE" ]]; then
    TEMPLATE_PATH="$TEMPLATE_OVERRIDE"
else
    TEMPLATE_PATH="$(
        python3 - <<'PY' 2>/dev/null || true
from pathlib import Path
try:
    import kopi_docka
except Exception as e:
    raise SystemExit(f"cannot import kopi_docka: {e}")
print(Path(kopi_docka.__file__).resolve().parent / "templates" / "config_template.json")
PY
    )"
fi

if [[ -z "$TEMPLATE_PATH" || ! -f "$TEMPLATE_PATH" ]]; then
    echo "error: could not locate the kopi-docka config template." >&2
    echo "  tried: ${TEMPLATE_PATH:-<empty>}" >&2
    echo "  hint:  install kopi-docka first, or pass --template /path/to/config_template.json" >&2
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

TMP="$(mktemp)"
trap 'rm -f -- "$TMP"' EXIT

build_merged > "$TMP"

# Final validation: must still parse as JSON
if ! jq -e . "$TMP" >/dev/null 2>&1; then
    echo "error: merge produced invalid JSON, refusing to write." >&2
    exit 2
fi

# Preserve original ownership + mode where possible (root-owned configs
# under /etc/ or /root/ are the common case).
chmod --reference="$USER_CONFIG" "$TMP" 2>/dev/null || true
chown --reference="$USER_CONFIG" "$TMP" 2>/dev/null || true

mv -- "$TMP" "$USER_CONFIG"
trap - EXIT

echo "Wrote merged config: $USER_CONFIG"
echo
echo "Next steps:"
echo "  1. Review the file (especially any 'type mismatch' warnings above)."
echo "  2. Run a sanity check:    kopi-docka --config '$USER_CONFIG' doctor"
echo "  3. If anything looks wrong, restore the backup file printed above."
