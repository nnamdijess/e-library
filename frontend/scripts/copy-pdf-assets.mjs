// Locally served, versioned PDF.js assets; no CDN or runtime external requests.
import { cp, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire(import.meta.url);
const pkg = require("pdfjs-dist/package.json");
const source = path.dirname(require.resolve("pdfjs-dist/package.json"));
const destination = path.resolve("public/pdfjs", pkg.version);
await mkdir(destination, { recursive: true });
await cp(path.join(source, "legacy/build/pdf.worker.min.mjs"), path.join(destination, "pdf.worker.min.mjs"));
for (const folder of ["cmaps", "standard_fonts", "wasm"]) await cp(path.join(source, folder), path.join(destination, folder), { recursive: true });
