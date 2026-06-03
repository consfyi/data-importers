# ConCat config proxy (Cloudflare Worker)

A tiny Cloudflare Worker that fetches a ConCat site's `/api/config` and passes
it through. It exists for cons (e.g. **furlingame**) whose own Cloudflare zone
403s the GitHub Actions importer by IP — a Worker's egress IP isn't blocked, so
the request gets through. (Cons on the shared ConCat platform use the
`CONCAT_RATELIMIT_KEY` header instead and don't need this.)

It's locked down so it can't be used as an open proxy: shared-secret required,
GET only, https only, path must be exactly `/api/config`, and the target host
must be in the `ALLOW_HOSTS` allowlist.

## Deploy (run in the consfyi Cloudflare account)

```sh
cd tools/data-importers/proxy
npx wrangler login                 # log into the cons.fyi Cloudflare account
npx wrangler secret put PROXY_SECRET   # paste a long random string; save it
npx wrangler deploy
```

`wrangler deploy` prints the URL, e.g. `https://consfyi-concat-proxy.<subdomain>.workers.dev`.

To allow another con later, add its host to `ALLOW_HOSTS` in `wrangler.toml` and
re-deploy.

## Wire it into the importer (consfyi/data repo secrets)

Set these on `consfyi/data` (Settings → Secrets and variables → Actions):

| name | value |
|---|---|
| `CONCAT_PROXY` | the Worker URL from `wrangler deploy` |
| `CONCAT_PROXY_SECRET` | the same string you gave `PROXY_SECRET` |
| `CONCAT_PROXY_HOSTS` | `reg.furlingame.com` (comma-separated for more) |

`import_concat.yml` passes all three to the importer. For any host in
`CONCAT_PROXY_HOSTS`, `import_concat.py` routes `/api/config` through the Worker;
every other con is fetched directly as before. If `CONCAT_PROXY` is unset the
importer behaves exactly as it does today.
