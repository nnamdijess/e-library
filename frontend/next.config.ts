import type { NextConfig } from "next";

const backendUrl = new URL(
  process.env.BACKEND_URL ?? "http://127.0.0.1:8000",
);

if (
  !["http:", "https:"].includes(backendUrl.protocol) ||
  backendUrl.username || backendUrl.password ||
  backendUrl.pathname !== "/" || backendUrl.search || backendUrl.hash
) {
  throw new Error("BACKEND_URL must be an HTTP(S) origin without credentials or a path.");
}

const config: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [{
      source: "/api/:path*",
      destination: `${backendUrl.origin}/api/:path*`,
    }];
  },
};

export default config;
