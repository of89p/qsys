import { cpSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const standaloneDir = path.join(root, ".next", "standalone");

if (!existsSync(standaloneDir)) {
  process.exit(0);
}

const publicDir = path.join(root, "public");
const standalonePublicDir = path.join(standaloneDir, "public");
if (existsSync(publicDir)) {
  cpSync(publicDir, standalonePublicDir, { recursive: true });
}

const staticDir = path.join(root, ".next", "static");
const standaloneStaticDir = path.join(standaloneDir, ".next", "static");
if (existsSync(staticDir)) {
  mkdirSync(path.dirname(standaloneStaticDir), { recursive: true });
  cpSync(staticDir, standaloneStaticDir, { recursive: true });
}
