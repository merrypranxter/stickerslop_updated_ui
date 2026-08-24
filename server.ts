import express from "express";
import path from "path";
import dotenv from "dotenv";
import { createServer as createViteServer } from "vite";

dotenv.config();

async function startServer() {
  const app = express();
  const PORT = 3000;

  // Search Giphy
  app.get("/api/giphy/search", async (req, res) => {
    try {
      const { q, type, offset } = req.query;
      const apiKey = process.env.GIPHY_API_KEY;
      if (!apiKey) {
        return res.status(500).json({ error: "GIPHY_API_KEY not configured in environment" });
      }
      const limit = 20;
      let endpoint = "gifs/search";
      if (type === "stickers") endpoint = "stickers/search";
      if (type === "text") endpoint = "text/search";
      
      const offsetParam = offset ? `&offset=${offset}` : "";
      const url = `https://api.giphy.com/v1/${endpoint}?api_key=${apiKey}&q=${encodeURIComponent(q as string)}&limit=${limit}${offsetParam}`;
      const response = await fetch(url);
      const data = await response.json();
      res.json(data);
    } catch (err) {
      console.error(err);
      res.status(500).json({ error: "Failed to search Giphy" });
    }
  });

  // Search Tenor
  app.get("/api/tenor/search", async (req, res) => {
    try {
      const { q, type, pos } = req.query;
      const apiKey = process.env.TENOR_API_KEY;
      if (!apiKey) {
        return res.status(500).json({ error: "TENOR_API_KEY not configured in environment" });
      }
      const limit = 20;
      let searchFilter = "";
      if (type === "stickers" || type === "text") {
         searchFilter = "&searchfilter=sticker,-static";
      }
      const posParam = pos ? `&pos=${pos}` : "";
      const url = `https://tenor.googleapis.com/v2/search?key=${apiKey}&q=${encodeURIComponent(q as string)}&limit=${limit}${searchFilter}${posParam}`;
      const response = await fetch(url);
      const data = await response.json();
      res.json(data);
    } catch (err) {
      console.error(err);
      res.status(500).json({ error: "Failed to search Tenor" });
    }
  });

  // Proxy for downloading image safely
  app.get("/api/proxy-image", async (req, res) => {
    try {
      const { url } = req.query;
      if (!url) return res.status(400).send("No URL");
      const response = await fetch(url as string);
      const buffer = await response.arrayBuffer();
      res.set("Content-Type", response.headers.get("Content-Type") || "image/gif");
      res.send(Buffer.from(buffer));
    } catch (err) {
      console.error(err);
      res.status(500).send("Proxy failed");
    }
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
