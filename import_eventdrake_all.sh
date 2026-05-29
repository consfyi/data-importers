#!/bin/bash
# Import all EventDrake-based sources in parallel.
#
# Third-party endpoints go down, expire their AppSync API keys, or block CI
# IPs from time to time. A single failing source must NOT prevent the sources
# that succeeded from being committed, so we collect failures, report them
# (as GitHub Actions annotations when available), and still exit 0.
script_dir="$(dirname -- "${BASH_SOURCE[0]:-$0}")"
import="$script_dir/import_eventdrake.py"

declare -A pids

run() {
    "$import" "$@" &
    pids[$!]="$*"
}

run furry-down-under.json https://ed.furdu.com.au furdu
run furconz-hotel.json https://furconz.org.nz hotel-
run furconz-camp.json https://furconz.org.nz camp-
run aurawra.json https://rego.aurawra.org ''
run tails-of-terror.json https://ed.furdu.com.au tot

failed=()
for pid in "${!pids[@]}"; do
    wait "$pid" || failed+=("${pids[$pid]}")
done

if (( ${#failed[@]} )); then
    echo "::error::import_eventdrake: ${#failed[@]} source(s) failed and were skipped:"
    for f in "${failed[@]}"; do
        echo "::error::  - ${f}"
    done
fi

# Exit 0 so successfully-imported sources are still committed even when some
# upstreams are down.
exit 0
