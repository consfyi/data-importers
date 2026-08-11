# Data importers

This repository contains all the data importers from external sources into cons.fyi data.

## `import_fancons.py`

This imports con information from [FanCons.com](https://fancons.com). This is the primary source of information. New cons will be imported into `import_pending` for verification. Note that attribution is required for use of data from FanCons.com, so a sources entry will be emitted in the output.

This importer **cannot** import the URL field, you must set them yourself.

## `import_concat.py`

This imports cons that are managed by [ConCat](https://concat.app) from any ConCat registration endpoint.

For all cons that support ConCat import, you can add an entry in `import_concat_all.sh`. Note that entries that have `fancons.com` as their source will be overriden if imported from ConCat.

This importer will infer the URL field from the registration (changes `https://reg.` to `https://`), so be careful if the heuristic is incorrect.

ConCat publishes next-year conventions before their details are settled, so a convention is skipped rather than imported when either:

* its venue is a placeholder (`Coming Soon`, `TBA`, `TBD`, ...), which would otherwise geocode to a confident but wrong location; or
* the year in its `longName` disagrees with the year its `startAt`/`endAt` fall in, which means the dates are the previous edition's, copied.

Both are logged as warnings, and the convention imports normally once the upstream data is real.

## Tests

`./test_import_concat.py` runs the importer unit tests offline (no ConCat endpoint, no Maps key). CI runs them on every PR.

## `import_furdu.py`

This imports cons that are managed by whatever registration system FurDU uses. This includes FurDU, Aurawra, and FurcoNZ.

This is super limited and can only really import start and end dates. Venue will be inferred from the previous event, which may or may not be what you want.

## `import_rams.py`

This imports only Midwest FurFest by scraping the landing page for dates and guessing everything else.

## `import_regfox.py`

This imports cons that are managed by [RegFox](https://regfox.com) from any RegFox endpoint.

This is super limited and can only really import start and end dates. Venue will be inferred from the previous event, which may or may not be what you want.
