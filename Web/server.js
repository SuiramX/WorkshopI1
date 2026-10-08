import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const port = Number(process.env.PORT || 3000);
const distDir = path.join(__dirname, "dist");

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".wasm": "application/wasm",
};

// In-memory cache for static files to prevent SD card / disk I/O bottlenecks on Raspberry Pi
const fileCache = new Map();

function getCachedFile(filePath) {
  if (fileCache.has(filePath)) {
    return fileCache.get(filePath);
  }
  try {
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      const content = fs.readFileSync(filePath);
      const ext = path.extname(filePath).toLowerCase();
      const contentType = MIME_TYPES[ext] || "application/octet-stream";
      const fileData = { content, contentType };
      fileCache.set(filePath, fileData);
      return fileData;
    }
  } catch (err) {
    console.error("Cache read error:", err);
  }
  return null;
}

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { allow: "GET, HEAD" });
    res.end();
    return;
  }

  const cleanUrl = req.url.split("?")[0];
  const safePath = path.normalize(decodeURIComponent(cleanUrl)).replace(/^(\.\.[\/\\])+/, "");
  let filePath = path.join(distDir, safePath);

  let cached = getCachedFile(filePath);
  const isHashedAsset = cleanUrl.startsWith("/assets/");

  if (!cached) {
    filePath = path.join(distDir, "index.html");
    cached = getCachedFile(filePath);
  }

  if (!cached) {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("404 Not Found");
    return;
  }

  const headers = {
    "content-type": cached.contentType,
    "content-length": cached.content.length,
  };

  // Cache static assets aggressively, keep index.html fresh
  if (isHashedAsset) {
    headers["cache-control"] = "public, max-age=31536000, immutable";
  } else {
    headers["cache-control"] = "public, max-age=0, must-revalidate";
  }

  res.writeHead(200, headers);
  res.end(req.method === "HEAD" ? undefined : cached.content);
});

const videoHost = process.env.VIDEO_HOST || "video";
const videoPort = Number(process.env.VIDEO_PORT || 8765);
const wsAuthToken = process.env.WS_AUTH_TOKEN || "";

server.on("upgrade", (req, clientSocket, head) => {
  // Disable Nagle algorithm on incoming client socket for instant low-latency delivery
  clientSocket.setNoDelay(true);

  let pathname = "/";
  try {
    pathname = new URL(req.url, `http://${req.headers.host || "localhost"}`).pathname;
  } catch {
    pathname = req.url.split("?")[0];
  }

  if (pathname === "/ws/video" || pathname === "/video" || pathname === "/ws") {
    const backendPath = `/video?token=${encodeURIComponent(wsAuthToken)}`;

    const backendReq = http.request({
      hostname: videoHost,
      port: videoPort,
      path: backendPath,
      method: "GET",
      headers: {
        ...req.headers,
        host: `${videoHost}:${videoPort}`,
      },
    });

    backendReq.on("upgrade", (backendRes, backendSocket, backendHead) => {
      // Disable Nagle algorithm on backend video socket
      backendSocket.setNoDelay(true);

      clientSocket.write(
        `HTTP/1.1 101 Switching Protocols\r\n` +
          Object.entries(backendRes.headers)
            .map(([k, v]) => `${k}: ${v}`)
            .join("\r\n") +
          "\r\n\r\n"
      );

      if (backendHead && backendHead.length > 0) {
        clientSocket.write(backendHead);
      }
      if (head && head.length > 0) {
        backendSocket.write(head);
      }

      backendSocket.pipe(clientSocket);
      clientSocket.pipe(backendSocket);

      const cleanup = () => {
        try {
          backendSocket.destroy();
        } catch (_) {}
        try {
          clientSocket.destroy();
        } catch (_) {}
      };

      backendSocket.on("error", cleanup);
      clientSocket.on("error", cleanup);
      backendSocket.on("close", cleanup);
      clientSocket.on("close", cleanup);
    });

    backendReq.on("error", (err) => {
      console.error("Erreur de proxy vers le flux vidéo backend:", err.message);
      try {
        clientSocket.write("HTTP/1.1 502 Bad Gateway\r\n\r\n");
      } catch (_) {}
      clientSocket.destroy();
    });

    backendReq.end();
  } else {
    try {
      clientSocket.write("HTTP/1.1 404 Not Found\r\n\r\n");
    } catch (_) {}
    clientSocket.destroy();
  }
});

server.listen(port, "0.0.0.0", () => {
  console.log(`Application web démarrée sur le port ${port}`);
  console.log(`Proxy WebSocket vidéo configuré vers ${videoHost}:${videoPort}`);
});
