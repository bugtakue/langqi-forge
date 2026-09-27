// Application shell (header/navigation). Rewritten by the application code.
// renderShell(root, ctx) must render the page frame into `root` and return the
// element into which the current page is rendered.
export async function renderShell(root, ctx) {
  root.innerHTML = '<header class="app-header"><a href="/" class="brand">App</a></header><main id="main"></main>';
  return root.querySelector('#main');
}
