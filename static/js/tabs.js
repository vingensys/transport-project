document.addEventListener("DOMContentLoaded", function () {
    const hash = window.location.hash;
    if (!hash) return;

    function activateTabByTarget(target) {
        const btn = document.querySelector(`button[data-bs-target="${target}"]`);
        if (!btn) {
            return false;
        }
        const tab = new bootstrap.Tab(btn);
        tab.show();
        return true;
    }

    // Inner tabs that live inside the Master Data main tab
    const masterInnerTargets = ["#company", "#lorry", "#location", "#authority"];

    if (masterInnerTargets.includes(hash)) {
        // First activate the Master Data main tab
        activateTabByTarget("#masterdata");
        // Then activate the inner tab (company/lorry/location/authority)
        activateTabByTarget(hash);
        return;
    }

    // Otherwise, try to activate a top-level tab directly
    activateTabByTarget(hash);
});
