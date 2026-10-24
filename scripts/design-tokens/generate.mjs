#!/usr/bin/env node
/**
 * 从 design/tokens.json 生成三端 token 文件。
 * 运行：node scripts/design-tokens/generate.mjs
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const tokens = JSON.parse(readFileSync(resolve(root, "design/tokens.json"), "utf8"));
const { brand, neutral, radius, space, font, breakpoint } = tokens;

function write(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content, "utf8");
  console.log("generated", path.replace(root + "/", ""));
}

const radiusVars = Object.entries(radius)
  .map(([k, v]) => `  --fa-radius-${k}: ${v}px;`)
  .join("\n");
const spaceVars = Object.entries(space)
  .map(([k, v]) => `  --fa-space-${k}: ${v}px;`)
  .join("\n");
const fontVars = Object.entries(font)
  .map(([k, v]) => `  --fa-font-${k}: ${v}px;`)
  .join("\n");

// ---- Web（SCSS 变量文件，import 到 styles/index.scss）----
write(
  resolve(root, "frontend/web/src/styles/core/_brand-tokens.generated.scss"),
  `// 由 design/tokens.json 生成，请勿手改。\n:root {\n  --fa-brand-blue: ${brand.blue};\n  --fa-brand-violet: ${brand.violet};\n  --fa-brand-gradient: ${brand.gradient};\n\n${radiusVars}\n${spaceVars}\n${fontVars}\n}\n\n.dark {\n  --fa-brand-ink: ${neutral.darkTextSecondary};\n}\n`
);

// ---- Docs（VitePress CSS 变量）----
write(
  resolve(root, "frontend/docs/.vitepress/theme/styles/brand-tokens.generated.css"),
  `/* 由 design/tokens.json 生成，请勿手改。 */\n:root {\n  --fa-brand-blue: ${brand.blue};\n  --fa-brand-violet: ${brand.violet};\n  --fa-brand-gradient: ${brand.gradient};\n  --vp-brand-gradient: ${brand.gradient};\n  --fa-border: ${neutral.border};\n}\n`
);

// ---- App（uni-app SCSS 变量）----
write(
  resolve(root, "frontend/app/src/styles/brand-tokens.generated.scss"),
  `/* 由 design/tokens.json 生成，请勿手改。 */\n$fa-brand-blue: ${brand.blue};\n$fa-brand-violet: ${brand.violet};\n$fa-border: ${neutral.border};\n$fa-radius-sm: ${radius.sm}px;\n$fa-radius-md: ${radius.md}px;\n$fa-radius-lg: ${radius.lg}px;\n$fa-ink: ${neutral.ink};\n$fa-text-secondary: ${neutral.textSecondary};\n`
);

console.log("done");
