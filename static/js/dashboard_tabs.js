document.addEventListener("DOMContentLoaded", function () {
  const root =
    document.body ||
    document.getElementById("dashboard-root");

  if (!root) return;

  const tab = root.dataset.defaultTab;
  if (!tab) return;

  // Find bootstrap tab trigger
  const trigger =
    document.querySelector(`[data-bs-toggle="tab"][data-bs-target="#${tab}"]`) ||
    document.querySelector(`[data-bs-toggle="tab"][href="#${tab}"]`);

  if (!trigger || typeof bootstrap === "undefined") return;

  const bsTab = new bootstrap.Tab(trigger);
  bsTab.show();

  // Optional: sync hash without reload
  if (window.location.hash !== `#${tab}`) {
    history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}#${tab}`
    );
  }
});
