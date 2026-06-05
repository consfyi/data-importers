// cons.fyi ConCat config proxy.
//
// Some ConCat registration sites (e.g. reg.furlingame.com, which is on its own
// Cloudflare zone rather than the shared ConCat platform) 403 requests from
// GitHub Actions runner IPs. Requests egressing from a Cloudflare Worker are
// not blocked, so this Worker fetches the upstream `/api/config` on the
// importer's behalf and passes the response straight through.
//
// Deliberately narrow so it can't be used as an open proxy:
//   - requires a shared secret (X-Proxy-Secret header == env.PROXY_SECRET)
//   - GET only
//   - https only
//   - the target path must be exactly `/api/config`
//   - the target host must be in env.ALLOW_HOSTS (comma-separated)
//
// Config (see proxy/README.md):
//   npx wrangler secret put PROXY_SECRET        # any long random string
//   [vars] ALLOW_HOSTS = "reg.furlingame.com"   # extend as more cons need it

export default {
  async fetch(request, env) {
    if (request.method !== "GET") {
      return new Response("method not allowed", { status: 405 });
    }
    if (!env.PROXY_SECRET || request.headers.get("x-proxy-secret") !== env.PROXY_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    const target = new URL(request.url).searchParams.get("url");
    if (!target) return new Response("missing ?url", { status: 400 });

    let t;
    try {
      t = new URL(target);
    } catch {
      return new Response("bad url", { status: 400 });
    }

    const allowHosts = (env.ALLOW_HOSTS || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    if (
      t.protocol !== "https:" ||
      t.pathname !== "/api/config" ||
      !allowHosts.includes(t.hostname)
    ) {
      return new Response("target not allowed", { status: 400 });
    }

    const upstream = await fetch(t.toString(), {
      headers: { "user-agent": "consfyi-importer (+https://cons.fyi)" },
      redirect: "follow",
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") || "application/json",
        "x-proxied-status": String(upstream.status),
      },
    });
  },
};
