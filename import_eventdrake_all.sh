#!/bin/bash
script_dir="$(dirname -- "${BASH_SOURCE[0]:-$0}")"
import="$script_dir/import_eventdrake.py"

cleanup() {
    local exit_code=0
    for pid in $(jobs -p); do
        wait "$pid" || exit_code=1
    done
    exit $exit_code
}

trap cleanup EXIT

$import furry-down-under.json https://furdu.com.au furdu &
$import furconz-hotel.json https://furconz.org.nz hotel- &
$import furconz-camp.json https://furconz.org.nz camp- &
$import aurawra.json https://rego.aurawra.org '' &
$import tails-of-terror.json https://furdu.com.au tot &
