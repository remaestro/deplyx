// Entry point for production SSR server
// Wraps the TanStack Start edge-style fetch handler into an HTTP server

import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const PORT = parseInt(process.env.PORT || "8080", 10);

async function start() {
  // Import the built server module
  const serverModule = await import("./dist/server/server.js");
  const handler = serverModule.default.fetch;

  const server = createServer(async (req, res) => {
    try {
      // Build a Request object from the Node.js IncomingMessage
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
