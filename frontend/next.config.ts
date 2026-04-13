import type { NextConfig } from "next";

const trameTarget =
  process.env.TRAME_INTERNAL_URL?.replace(/\/$/, "") || "http://127.0.0.1:8090";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    // Used by `next dev` (and non-minimal servers). Standalone production ignores these
    // rewrites; the app uses NEXT_PUBLIC_TRAME_VIEWER_URL for the iframe instead.
    return [
      { source: "/viewer", destination: `${trameTarget}/` },
      { source: "/viewer/", destination: `${trameTarget}/` },
      { source: "/viewer/:path*", destination: `${trameTarget}/:path*` },
    ];
  },
};

export default nextConfig;
