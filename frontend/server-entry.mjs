// Entry point for production SSR server
// Wraps the TanStack Start edge-style fetch handler into an HTTP server

import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, extname } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const PORT = parseInt(process.env.PORT || "8080", 10);

// MIME types for static files
const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".eot": "application/vnd.ms-fontobject",
  ".webp": "image/webp",
};

const CLIENT_DIR = join(__dirname, "dist", "client");

async function start() {
  // Import the built server module
  const serverModule = await import("./dist/server/server.js");
  const handler = serverModule.default.fetch;

  const server = createServer(async (req, res) => {
    try {
      const urlPath = new URL(req.url || "/", "http://localhost").pathname;

      // ── Serve static files from dist/client/ ───────────────
      if (req.method === "GET" && !urlPath.startsWith("/api/")) {
        const filePath = join(CLIENT_DIR, urlPath === "/" ? "index.html" : urlPath);
        if (existsSync(filePath)) {
          const ext = extname(filePath);
          const mime = MIME_TYPES[ext] || "application/octet-stream";
          const content = readFileSync(filePath);
          res.writeHead(200, { "Content-Type": mime, "Cache-Control": ext === ".html" ? "no-cache" : "public, max-age=31536000, immutable" });
          res.end(content);
          return;
        }
      }

      // ── Fallback: SSR handler ──────────────────────────────
      const protocol = req.socket.encrypted ? "https" : "http";
      const host = req.headers.host || "localhost";
      const url = new URL(req.url || "/", `${protocol}://${host}`);

      const request = new Request(url, {
        method: req.method,
        headers: req.headers,
        body: req.method !== "GET" && req.method !== "HEAD" ? req : undefined,
        duplex: "half",
      });

      const response = await handler(request, {}, {});

      // Write response headers
      res.statusCode = response.status;
      response.headers.forEach((value, key) => {
        res.setHeader(key, value);
      });

      // Write response body
      if (response.body) {
        const reader = response.body.getReader();
        const pump = () => {
          reader.read().then(({ done, value }) => {
            if (done) {
              res.end();
              return;
            }
            res.write(value);
            pump();
          }).catch((err) => {
            console.error("Stream error:", err);
            res.end();
          });
        };
        pump();
      } else {
        res.end();
      }
    } catch (err) {
      console.error("Request error:", err);
      res.statusCode = 500;
      res.end("Internal Server Error");
    }
  });

  server.listen(PORT, () => {
    console.log(`Deplyx frontend SSR server listening on port ${PORT}`);
  });
}

start().catch((err) => {
  console.error("Failed to start server:", err);
  process.exit(1);
});
