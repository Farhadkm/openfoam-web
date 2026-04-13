/**
 * Browser-visible origin of the Trame viewer (no trailing slash).
 * For Docker standalone builds, set `NEXT_PUBLIC_TRAME_VIEWER_URL` at build time
 * (e.g. `http://localhost:8090`). For `next dev`, `/viewer` rewrites can proxy instead.
 */
export function tramePublicOrigin(): string {
  return (process.env.NEXT_PUBLIC_TRAME_VIEWER_URL || "").replace(/\/$/, "");
}

/** True if a postMessage event came from the configured Trame origin (treats localhost ↔ 127.0.0.1). */
export function trameOriginAcceptsMessage(tramePublicUrl: string, eventOrigin: string): boolean {
  const base = tramePublicUrl.replace(/\/$/, "");
  if (!base || !eventOrigin) return false;
  if (eventOrigin === base) return true;
  try {
    const t = new URL(base);
    const e = new URL(eventOrigin);
    if (t.protocol !== e.protocol) return false;
    const tp = t.port || (t.protocol === "https:" ? "443" : "80");
    const ep = e.port || (e.protocol === "https:" ? "443" : "80");
    if (tp !== ep) return false;
    if (t.hostname === e.hostname) return true;
    const loopback = (h: string) => h === "localhost" || h === "127.0.0.1" || h === "[::1]";
    return loopback(t.hostname) && loopback(e.hostname);
  } catch {
    return false;
  }
}

const TRAME_EMBED_CACHE_TAG = "oe_embed_v14";

/** Hash fragment keeps `jobId` if the query string is rewritten. */
export function trameEmbedFragment(jobId: string): string {
  return `#embed=openfoam-canvas&jobId=${encodeURIComponent(jobId)}`;
}

/**
 * Direct ws URL to the Trame host avoids vtk.js SessionManager / paraview probe (reliable after refresh).
 * Only set when `NEXT_PUBLIC_TRAME_VIEWER_URL` is set — using `window.location.origin` would point at
 * Next.js (:3000) under `next dev` /viewer proxy and break the socket.
 */
function appendSessionUrl(query: URLSearchParams): void {
  const pub = tramePublicOrigin();
  if (!pub) return;
  const wsProto = pub.startsWith("https") ? "wss:" : "ws:";
  try {
    const u = new URL(pub);
    query.set("sessionURL", `${wsProto}//${u.host}/ws`);
  } catch {
    /* omit sessionURL */
  }
}

function trameAppUrl(jobId: string, query: URLSearchParams): string {
  appendSessionUrl(query);
  const qs = query.toString();
  const frag = trameEmbedFragment(jobId);
  const pub = tramePublicOrigin();
  if (pub) return `${pub}/?${qs}${frag}`;
  if (typeof window !== "undefined") {
    return `${window.location.origin}/viewer/?${qs}${frag}`;
  }
  return `/viewer/?${qs}${frag}`;
}

/** Open the VTK viewer in a new tab. */
export function trameViewerSrc(jobId: string): string {
  return trameAppUrl(jobId, new URLSearchParams({ jobId }));
}

/** Embedded iframe URL; pass `parentOrigin` when Trame is on another origin (e.g. Docker). */
export function trameCanvasViewerSrc(jobId: string, parentOrigin?: string): string {
  const q = new URLSearchParams({ jobId, embed: "canvas", [TRAME_EMBED_CACHE_TAG]: "1" });
  if (parentOrigin) q.set("parentOrigin", parentOrigin);
  return trameAppUrl(jobId, q);
}

/** Target origin for `postMessage` into the Trame iframe. */
export function trameFramePostMessageTarget(): string {
  const pub = tramePublicOrigin();
  if (pub) return pub;
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}
