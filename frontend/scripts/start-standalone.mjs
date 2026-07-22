import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const nextEnv = require("@next/env");
const { loadEnvConfig } = nextEnv;

loadEnvConfig(path.resolve(process.cwd(), ".."));

await import("../.next/standalone/server.js");
