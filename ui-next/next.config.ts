import type { NextConfig } from "next";

const API_BACKEND = process.env.API_BACKEND_URL || "http://oak-api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/oak-api/:path*", destination: `${API_BACKEND}/:path*` },
    ];
  },
};

export default nextConfig;
