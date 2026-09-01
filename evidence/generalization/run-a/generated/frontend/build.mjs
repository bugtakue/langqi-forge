import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";

const source = path.resolve("src");
const target = path.resolve("dist");
await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
console.log("frontend built");
