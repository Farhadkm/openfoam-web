/**
 * Browser-visible Trame viewer URLs via the BFF (`NEXT_PUBLIC_API_URL` + `/viewer`).
 */

/** BFF base URL (no trailing slash). */
export function apiPublicBase(): string {
  return (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
}

/** Trame iframe base path on the BFF (no trailing slash). */
export function tramePublicOrigin(): string {
  return `${apiPublicBase()}/viewer`;
}

/** True if a postMessage event came from the Trame iframe origin (treats localhost ↔ 127.0.0.1). */
export function trameOriginAcceptsMessage(tramePublicUrl: string, eventOrigin: string): boolean {
  if (!tramePublicUrl || !eventOrigin) return false;
  try {
    const expected = new URL(tramePublicUrl).origin;
    const actual = new URL(eventOrigin).origin;
    if (actual === expected) return true;
    const t = new URL(expected);
    const e = new URL(actual);
    if (t.protocol !== e.protocol) return false;
    const tp = t.port || (t.protocol === "https:" ? "443" : "80");
    const ep = e.port || (e.protocol === "https:" ? "443" : "80");
    if (tp !== ep) return false;
    const loopback = (h: string) => h === "localhost" || h === "127.0.0.1" || h === "[::1]";
    return loopback(t.hostname) && loopback(e.hostname);
  } catch {
    return false;
  }
}

const TRAME_EMBED_CACHE_TAG = "oe_embed_v14";

/** Hash fragment keeps `jobId` if the query string is rewritten. */
export function trameEmbedFragment(jobId: string): string {
  return `#embed=forge-canvas&jobId=${encodeURIComponent(jobId)}`;
}

/** wslink session URL on the BFF viewer proxy (reliable after refresh). */
function appendSessionUrl(query: URLSearchParams): void {
  const base = tramePublicOrigin();
  const wsProto = base.startsWith("https") ? "wss:" : "ws:";
  try {
    const u = new URL(base);
    const wsPath = `${u.pathname.replace(/\/$/, "")}/ws`;
    query.set("sessionURL", `${wsProto}//${u.host}${wsPath}`);
  } catch {
    /* omit sessionURL */
  }
}

function trameAppUrl(jobId: string, query: URLSearchParams): string {
  appendSessionUrl(query);
  const qs = query.toString();
  const frag = trameEmbedFragment(jobId);
  return `${tramePublicOrigin()}/?${qs}${frag}`;
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

/** Target origin for `postMessage` into the Trame iframe (scheme + host + port). */
export function trameFramePostMessageTarget(): string {
  try {
    return new URL(tramePublicOrigin()).origin;
  } catch {
    return typeof window !== "undefined" ? window.location.origin : "";
  }
}
