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
$import anthroexpo.json https://reg.anthroexpo.net &
$import bewhiskered.json https://reg.bewhiskeredcon.org &
$import biggest-little-fur-con.json https://reg.goblfc.org &
$import carolina-furfare.json https://reg.carolinafurfare.org &
$import furcationland.json https://reg.furcationland.org &
$import furski.json https://reg.fur.ski &
$import further-confusion.json https://reg.furtherconfusion.org &
$import furvana.json https://reg.furvana.org &
$import indyfurcon.json https://reg.indyfurcon.com &
$import its-ruff-out.json https://reg.ruffout.org &
$import las-vegas-fur-con.json https://reg.lasvegasfurcon.org &
$import megaplex.json https://reg.megaplexcon.org &
$import pawcon.json https://reg.pacanthro.org &
$import woods-flock.json https://reg.woodsflock.com &
