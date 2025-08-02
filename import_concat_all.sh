#!/bin/bash
script_dir="$(dirname -- "${BASH_SOURCE[0]:-$0}")"
import="$script_dir/concat_importer.py"

cleanup() {
    local exit_code=0
    for pid in $(jobs -p); do
        wait "$pid" || exit_code=1
    done
    exit $exit_code
}

trap cleanup EXIT

$import anthrocon.json https://reg.anthrocon.org &
$import las-vegas-fur-con.json https://reg.lasvegasfurcon.org &
$import megaplex.json https://reg.megaplexcon.org &
$import further-confusion.json https://reg.furtherconfusion.org &
$import biggest-little-fur-con.json https://reg.goblfc.org &
$import pawcon.json https://reg.pacanthro.org &
$import anthroexpo.json https://reg.anthroexpo.net &
