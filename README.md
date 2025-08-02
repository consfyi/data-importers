# Data importers

This repository contains all the data importers from external sources into cons.fyi data.

## `fancons_importer.py`

This imports con information from [FanCons.com](https://fancons.com). This is the primary source of information. New cons will be imported into `import_pending` for verification. Note that attribution is required for use of data from FanCons.com, so a sources entry will be emitted in the output.

This importer **cannot** import the URL field, you must set them yourself.

## `concat_importer.py`

This imports cons that are managed by [ConCat](https://concat.app) from any ConCat registration endpoint.

For all cons that support ConCat import, you can add an entry in `import_concat_all.sh` and also add an entry in `fancons_ignore` to ignore it during FanCons.com import.

This importer will infer the URL field from the registration (changes `https://reg.` to `https://`), so be careful if the heuristic is incorrect.

## `regfox_importer.py`

This imports cons that are managed by [RegFox](https://regfox.com) from any RegFox endpoint.

This is super limited and can only really import start and end dates. Venue will be inferred from the previous event, which may or may not be what you want.
