function clampDimension(value, fallback, min, max) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, Math.round(numeric)));
}

function normalizeOllamaEndpoint(value) {
  let url;
  try {
    url = new URL(String(value || "").trim());
  } catch (_) {
    throw new Error("Enter a valid HTTP or HTTPS Ollama endpoint.");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("The endpoint must use HTTP or HTTPS.");
  }
  if (url.username || url.password) {
    throw new Error("Do not put credentials in the endpoint URL.");
  }
  url.hash = "";
  const path = url.pathname.replace(/\/+$/, "");
  if (!path.endsWith("/api/chat")) url.pathname = `${path}/api/chat`;
  return url.toString();
}

async function renderMarkdownAnswer(MarkdownRenderer, app, markdown, element, sourcePath, component) {
  return MarkdownRenderer.render(app, markdown, element, sourcePath, component);
}

module.exports = {
  clampDimension,
  normalizeOllamaEndpoint,
  renderMarkdownAnswer
};
