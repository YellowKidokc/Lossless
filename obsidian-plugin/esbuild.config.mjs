import { build } from "esbuild";
import { mkdir, cp } from "fs/promises";
import { join } from "path";

const isProd = process.argv.includes("production");

const outdir = "dist";

async function bundle() {
  await build({
    entryPoints: ["src/main.ts"],
    bundle: true,
    outfile: join(outdir, "main.js"),
    format: "cjs",
    platform: "browser",
    sourcemap: !isProd,
    target: "es2018",
    external: ["obsidian"],
  });

  await mkdir(outdir, { recursive: true });
  await cp("manifest.json", join(outdir, "manifest.json"), { recursive: false });
  await cp("styles.css", join(outdir, "styles.css"), { recursive: false });
  console.log(`Built plugin (${isProd ? "production" : "dev"})`);
}

bundle().catch((err) => {
  console.error(err);
  process.exit(1);
});
