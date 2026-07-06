// INERT self-test fixture: memorizes the sample fixture instead of wiring
// the fetch response. Renders correctly against the ORIGINAL fixture but
// will NOT change when the grader swaps in the mutated fixture - this is
// the case the S6 anti-dodge / real-data-proof check must catch.
function render() {
  const app = document.getElementById("app");
  app.innerHTML = "";
  const hardcoded = [
    { name: "prov-a", cost_class: "cheap", status: "ok" },
    { name: "prov-b", cost_class: "strong", status: "degraded" },
    { name: "prov-c", cost_class: "premium", status: "down" },
  ];
  for (const p of hardcoded) {
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

// Calls fetch (so a naive "did it call fetch at all" check wouldn't catch
// this) but discards the response - the classic dodge.
fetch("/charon/status").then(() => render());
