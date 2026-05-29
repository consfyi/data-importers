#!/bin/bash
# Import all furry.nz-based sources in parallel.
#
# furry.nz (the anthro.nz hub) publishes these cons' dates as schema.org
# JSON-LD, replacing the per-con EventDrake/AppSync backends. As with the
# other importers, a single failing source must not block the ones that
# succeeded, so failures are reported (as GitHub Actions annotations when
# available) and the script still exits 0.
script_dir="$(dirname -- "${BASH_SOURCE[0]:-$0}")"
import="$script_dir/import_furrynz.py"

declare -A pids

run() {
    "$import" "$@" &
    pids[$!]="$*"
}

run furconz-hotel.json furconz furconz-hotel
run furconz-camp.json furconz furconz-camp
run furry-down-under.json furdu furdu
run tails-of-terror.json furdu tails-of-terror
run aurawra.json aurawra

failed=()
for pid in "${!pids[@]}"; do
    wait "$pid" || failed+=("${pids[$pid]}")
done

if (( ${#failed[@]} )); then
    echo "::error::import_furrynz: ${#failed[@]} source(s) failed and were skipped:"
    for f in "${failed[@]}"; do
        echo "::error::  - ${f}"
    done
fi

# Exit 0 so successfully-imported sources are still committed even when some
# upstreams are down.
exit 0
