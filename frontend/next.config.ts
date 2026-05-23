import type { NextConfig } from "next";

const bffTarget =
  process.env.BFF_INTERNAL_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    // Optional dev convenience: localhost:3000/viewer → BFF /viewer (iframe uses BFF directly).
    return [
      { source: "/viewer", destination: `${bffTarget}/viewer` },
      { source: "/viewer/", destination: `${bffTarget}/viewer/` },
      { source: "/viewer/:path*", destination: `${bffTarget}/viewer/:path*` },
    ];
  },
};

export default nextConfig;
