import type { NextConfig } from "next";

const backendUrl = new URL(
  process.env.BACKEND_URL ?? "http://127.0.0.1:8000",
);
const maxUploadBytes = Number(process.env.EBOOK_MAX_UPLOAD_BYTES ?? 104857600);
if (!Number.isSafeInteger(maxUploadBytes) || maxUploadBytes < 1024 || maxUploadBytes > 1073741824) {
  throw new Error("EBOOK_MAX_UPLOAD_BYTES must be an integer from 1024 to 1073741824.");
}

if (
  !["http:", "https:"].includes(backendUrl.protocol) ||
  backendUrl.username || backendUrl.password ||
  backendUrl.pathname !== "/" || backendUrl.search || backendUrl.hash
) {
  throw new Error("BACKEND_URL must be an HTTP(S) origin without credentials or a path.");
}

const config: NextConfig = {
  poweredByHeader: false,
  experimental: {
    // External rewrites clone request bodies. Keep their buffer above the file
    // limit plus multipart overhead, and let FastAPI enforce actual file bytes.
    proxyClientMaxBodySize: maxUploadBytes + 64 * 1024,
    proxyTimeout: 180000,
  },
  async rewrites() {
    return [{
      source: "/api/:path*",
      destination: `${backendUrl.origin}/api/:path*`,
    }];
  },
};

export default config;
