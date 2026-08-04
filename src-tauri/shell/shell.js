// The shell injects `__BRFV2_FAILURE__` from Rust before the document loads.
// Text is assigned through textContent only — the failure detail is untrusted
// operational output (paths, exit codes, stderr) and must never be parsed as
// markup.
const failure = globalThis.__BRFV2_FAILURE__ ?? {};
const detail = document.getElementById('detail');

if (typeof failure.headline === 'string' && failure.headline.trim()) {
  const headline = document.getElementById('headline');
  headline.textContent = failure.headline;
  document.title = `Träff — ${failure.headline}`;
}

// Flip data-state exactly once, so neither a reader nor the acceptance harness
// can mistake the pre-script placeholder for the actual cause.
if (typeof failure.detail === 'string' && failure.detail.trim()) {
  detail.textContent = failure.detail;
  detail.dataset.state = 'applied';
} else {
  detail.textContent = 'Okänt fel — ingen orsak kunde läsas ut.';
  detail.dataset.state = 'unknown';
}
