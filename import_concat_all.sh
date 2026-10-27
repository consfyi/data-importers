#!/bin/bash
# Import all ConCat-based sources in parallel.
#
# Third-party registration endpoints go down, expire keys, or block CI IPs
# from time to time. A single failing source must NOT prevent the sources
# that succeeded from being committed, so we collect failures, report them
# (as GitHub Actions annotations when available), and still exit 0.
#
# If CONCAT_FAILURES_FILE is set, each failed source is also written there as
# one line, with the last line of its error output, so the caller can fail the
# run after committing what did import. The file is emptied first and stays
# empty when every source imports. If the file can't be written, the script
# exits 2, since an unwritten report would hide the failures.
script_dir="$(dirname -- "${BASH_SOURCE[0]:-$0}")"
import="${IMPORT_CONCAT:-$script_dir/import_concat.py}"

logs="$(mktemp -d)"
trap 'rm -rf "$logs"' EXIT

# A report that can't be written would hide every failure, so stop before
# importing anything.
if [[ -n "$CONCAT_FAILURES_FILE" ]] && ! : > "$CONCAT_FAILURES_FILE"; then
    echo "::error::import_concat: can't write CONCAT_FAILURES_FILE ($CONCAT_FAILURES_FILE)"
    exit 2
fi

declare -A pids
declare -A errlogs

# Each source's stderr goes to its own file so its error can be reported
# below; the files are printed once every source has finished.
run() {
    local errlog="$logs/${#pids[@]}.log"
    "$import" "$@" 2> "$errlog" &
    pids[$!]="$*"
    errlogs[$!]="$errlog"
}

run anthrocon.json https://reg.anthrocon.org
run anthroexpo.json https://reg.anthroexpo.net
run aquatifur.json https://reg.aquatifur.org
run bewhiskered.json https://reg.bewhiskeredcon.org
run biggest-little-fur-con.json https://reg.goblfc.org
run carolina-furfare.json https://reg.carolinafurfare.org
run denfur.json https://reg.denfur.org
run furcationland.json https://reg.furcationland.org
run furlingame.json https://reg.furlingame.com
run furski.json https://reg.fur.ski
run further-confusion.json https://reg.furtherconfusion.org
run furvana.json https://reg.furvana.org
run indyfurcon.json https://reg.indyfurcon.com
run its-ruff-out.json https://reg.ruffout.org
run las-vegas-fur-con.json https://reg.lasvegasfurcon.org
run megaplex.json https://reg.megaplexcon.org
run palmetto-fur-the-season.json https://reg.palmettofurtheseason.org
run pawcon.json https://reg.pacanthro.org
run woods-flock.json https://reg.woodsflock.com

failed=()
for pid in "${!pids[@]}"; do
    if ! wait "$pid"; then
        # One line, bounded: the error text can come from the upstream site.
        reason="$(grep -v '^[[:space:]]*$' "${errlogs[$pid]}" | tail -n 1 | tr -d '\r' | cut -c1-300)"
        failed+=("${pids[$pid]}: ${reason:-no error output}")
    fi
    cat "${errlogs[$pid]}" >&2
done

if (( ${#failed[@]} )); then
    echo "::error::import_concat: ${#failed[@]} source(s) failed and were skipped:"
    for f in "${failed[@]}"; do
        echo "::error::  - ${f}"
    done
    if [[ -n "$CONCAT_FAILURES_FILE" ]] &&
        ! printf '%s\n' "${failed[@]}" > "$CONCAT_FAILURES_FILE"; then
        echo "::error::import_concat: can't write CONCAT_FAILURES_FILE ($CONCAT_FAILURES_FILE)"
        exit 2
    fi
fi

# Exit 0 so successfully-imported sources are still committed even when some
# upstreams are down.
exit 0
