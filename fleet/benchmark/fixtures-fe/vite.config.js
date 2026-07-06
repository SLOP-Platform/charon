import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Preconfigured build toolchain - the model is not scored on tooling setup,
// only on the component/app source (src/**). `npm run build` -> dist/bundle.js
// as a single self-executing (IIFE) script, so the hidden grader can load it
// straight into jsdom without an ES-module loader.
export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: "dist",
    rollupOptions: {
      input: "src/main.js",
      output: {
        format: "iife",
        entryFileNames: "bundle.js",
        inlineDynamicImports: true,
      },
    },
  },
});
