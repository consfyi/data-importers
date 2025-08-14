#!/bin/bash
script_dir="$(dirname -- "${BASH_SOURCE[0]:-$0}")"
import="$script_dir/import_furdu.py"

cleanup() {
    local exit_code=0
    for pid in $(jobs -p); do
        wait "$pid" || exit_code=1
    done
    exit $exit_code
}

trap cleanup EXIT

$import furry-down-under.json https://p5ondbudkzgh5ikfuxmecccwh4.appsync-api.ap-southeast-2.amazonaws.com da2-plp44ele4jb3hcnnnkcod3pe34 furdu &
$import furconz-hotel.json https://bzyicmepsfffzcxo3a5tldiamu.appsync-api.ap-southeast-2.amazonaws.com da2-uv7fhpcegvey7ouevbtdmxwvv4 hotel- &
$import furconz-camp.json https://bzyicmepsfffzcxo3a5tldiamu.appsync-api.ap-southeast-2.amazonaws.com da2-uv7fhpcegvey7ouevbtdmxwvv4 camp- &
$import aurawra.json https://i72iwzmi5bcono4xo75ynmbf7q.appsync-api.ap-southeast-2.amazonaws.com da2-5mayemxyszbuteiwbkfdtpqjim '' &
$import tails-of-terror.json https://p5ondbudkzgh5ikfuxmecccwh4.appsync-api.ap-southeast-2.amazonaws.com da2-plp44ele4jb3hcnnnkcod3pe34 tot &
