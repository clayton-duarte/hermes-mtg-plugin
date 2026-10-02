(function () {
  // Deck Lab's tab is hidden (manifest.json tab.hidden = true); this plugin
  // only exposes backend API routes under /api/plugins/deck-lab/. The
  // placeholder registration below is required by the dashboard's UI
  // plugin contract even for a hidden, API-only plugin -- it never renders
  // because there is no nav tab to reach it from.
  window.__HERMES_PLUGINS__.register("deck-lab", function () {
    return null;
  });
})();
