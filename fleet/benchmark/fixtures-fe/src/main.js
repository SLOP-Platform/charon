import App from "./App.svelte";

// TODO (model task): this bare-bones mount is already wired; you should not
// need to change this file. Prefer Svelte (edit App.svelte). If you cannot
// get a working Svelte build, plain vanilla JS with no framework is an
// acceptable fallback (in which case you may replace the contents of this
// file entirely and remove the Svelte import above).
new App({
  target: document.getElementById("app"),
});
