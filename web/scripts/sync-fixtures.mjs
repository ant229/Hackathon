// Copies the shared contract files from ../fixtures into src/data so the app can import them.
// Runs automatically before `npm run dev` and `npm run build`.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "fixtures");
const dest = join(here, "..", "src", "data");
mkdirSync(dest, { recursive: true });

for (const f of ["zones.geojson", "sample_responses.json"]) {
  if (existsSync(join(src, f))) {
    copyFileSync(join(src, f), join(dest, f === "zones.geojson" ? "zones.json" : f));
  } else {
    console.warn(`sync-fixtures: ${f} not found in ../fixtures, keeping committed copy`);
  }
}
console.log("sync-fixtures: fixtures copied to src/data");
