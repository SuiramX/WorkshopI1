const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const port = Number(process.env.PORT || 3000);
const indexPath = path.join(__dirname, "public", "index.html");

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

  if (req.url !== "/" && req.url !== "/index.html") {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("Page introuvable");
    return;
  }

  fs.readFile(indexPath, (error, content) => {
    if (error) {
      console.error("Impossible de lire la page d'accueil :", error);
      res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
      res.end("Erreur interne du serveur");
      return;
    }

    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(req.method === "HEAD" ? undefined : content);
  });
});

server.listen(port, "0.0.0.0", () => {
  console.log(`Application web démarrée sur le port ${port}`);
});
