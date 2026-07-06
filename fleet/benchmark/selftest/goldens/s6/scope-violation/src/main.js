// Vanilla-JS fallback solution (no framework) - App.svelte intentionally
// unused; this file is the sole entry per vite.config.js's `input`.
async function render() {
  const res = await fetch("/charon/status");
  const providers = await res.json();
  const app = document.getElementById("app");
  app.innerHTML = "";
  for (const p of providers) {
    const row = document.createElement("div");
    row.setAttribute("data-testid", "provider-row");

    const name = document.createElement("span");
    name.setAttribute("data-testid", "name");
    name.textContent = p.name;

    const costClass = document.createElement("span");
    costClass.setAttribute("data-testid", "cost_class");
    costClass.textContent = p.cost_class;

    const status = document.createElement("span");
    status.setAttribute("data-testid", "status");
    status.textContent = p.status;

    row.appendChild(name);
    row.appendChild(costClass);
    row.appendChild(status);
    app.appendChild(row);
  }
}

render();
