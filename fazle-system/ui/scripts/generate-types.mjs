#!/usr/bin/env node
// ============================================================
// WBOM — OpenAPI → Frontend Types Generator
// Fetches /openapi.json from the WBOM backend and generates
// JSDoc type definitions for frontend usage.
//
// Usage:
//   node scripts/generate-types.mjs                       # from VPS
//   node scripts/generate-types.mjs http://localhost:9900  # local
// ============================================================

const BASE = process.argv[2] || "http://localhost:9900";
const OPENAPI_URL = `${BASE}/openapi.json`;
const OUTPUT = new URL("../src/lib/wbom-types.generated.js", import.meta.url);

import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

async function main() {
  console.log(`Fetching OpenAPI spec from ${OPENAPI_URL} ...`);
  const res = await fetch(OPENAPI_URL);
  if (!res.ok) {
    console.error(`Failed: ${res.status} ${res.statusText}`);
    process.exit(1);
  }
  const spec = await res.json();
  const schemas = spec.components?.schemas || {};

  const lines = [
    "// ============================================================",
    "// AUTO-GENERATED — do not edit manually",
    `// Source: ${OPENAPI_URL}`,
    `// Generated: ${new Date().toISOString()}`,
    "// ============================================================",
    "",
  ];

  // Generate JSDoc typedefs for each schema
  for (const [name, schema] of Object.entries(schemas)) {
    if (!schema.properties) continue;
    lines.push(`/**`);
    lines.push(` * @typedef {Object} ${name}`);
    for (const [prop, def] of Object.entries(schema.properties)) {
      const jsType = openApiToJsType(def);
      const req = (schema.required || []).includes(prop);
      const opt = req ? "" : "=";
      const desc = def.description ? ` - ${def.description}` : "";
      lines.push(` * @property {${jsType}${opt}} ${prop}${desc}`);
    }
    lines.push(` */`);
    lines.push("");
  }

  lines.push("export {};");
  lines.push("");

  const outPath = fileURLToPath(OUTPUT);
  writeFileSync(outPath, lines.join("\n"), "utf-8");
  console.log(`Generated ${Object.keys(schemas).length} type(s) → ${outPath}`);
}

function openApiToJsType(def) {
  if (def.anyOf) {
    const types = def.anyOf.map(openApiToJsType).filter((t) => t !== "null");
    return types.length ? `${types.join("|")}|null` : "any";
  }
  if (def.$ref) {
    return def.$ref.split("/").pop();
  }
  switch (def.type) {
    case "integer":
    case "number":
      return "number";
    case "string":
      return "string";
    case "boolean":
      return "boolean";
    case "array":
      return `Array<${def.items ? openApiToJsType(def.items) : "any"}>`;
    case "object":
      return "Object";
    case "null":
      return "null";
    default:
      return "any";
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
