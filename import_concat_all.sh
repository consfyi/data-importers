#!/bin/bash
# Import all ConCat-based sources in parallel.
#
# Third-party registration endpoints go down, expire keys, or block CI IPs
# from time to time. A single failing source must NOT prevent the sources
# that succeeded from being committed, so we collect failures, report them
# (as GitHub Actions annotations when available), and still exit 0.
script_dir="$(dirname -- "${BASH_SOURCE[0]:-$0}")"
import="$script_dir/import_concat.py"

declare -A pids

run() {
    "$import" "$@" &
    pids[$!]="$*"
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
    wait "$pid" || failed+=("${pids[$pid]}")
done

if (( ${#failed[@]} )); then
    echo "::error::import_concat: ${#failed[@]} source(s) failed and were skipped:"
    for f in "${failed[@]}"; do
        echo "::error::  - ${f}"
    done
fi

# Exit 0 so successfully-imported sources are still committed even when some
# upstreams are down.
exit 0
