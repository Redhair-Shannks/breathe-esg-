import { mkdir, writeFile } from "node:fs/promises";

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Breathe ESG Ingestion Review</title>
    <link rel="stylesheet" href="/static/assets/main.css?v=20260529-4" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/static/assets/main.js?v=20260529-4"></script>
  </body>
</html>
`;

await mkdir(new URL("./dist", import.meta.url), { recursive: true });
await writeFile(new URL("./dist/index.html", import.meta.url), html);
