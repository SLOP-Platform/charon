<script>
  let providers = [];

  async function load() {
    const res = await fetch("/charon/status");
    providers = await res.json();
  }

  load();
</script>

<div id="provider-list">
  {#each providers as p}
    <div data-testid="provider-row">
      <span data-testid="name">{p.name}</span>
      <span data-testid="cost_class">{p.cost_class}</span>
      <span data-testid="status">{p.status}</span>
    </div>
  {/each}
</div>
