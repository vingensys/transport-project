// static/js/location.js

document.addEventListener("DOMContentLoaded", function () {
  // ---------------------------------------
  // Go-to-page logic for Locations pagination
  // ---------------------------------------
  const form = document.getElementById("locGotoForm");
  if (form) {
    const input = document.getElementById("locGotoInput");
    const btn = document.getElementById("locGotoBtn");
    const baseUrl = form.getAttribute("data-base-url");
    const maxPages = parseInt(form.getAttribute("data-max-pages"), 10);

    function goToPage() {
      if (!input || !baseUrl || !maxPages) return;
      let p = parseInt(input.value, 10);
      if (isNaN(p)) return;
      if (p < 1) p = 1;
      if (p > maxPages) p = maxPages;
      window.location.href = baseUrl + "?loc_page=" + p + "#location";
    }

    if (btn) {
      btn.addEventListener("click", goToPage);
    }

    if (input) {
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          goToPage();
        }
      });
    }
  }

  // ---------------------------------------
  // Simple client-side filter for locations table
  // ---------------------------------------
  (function setupTableFilter() {
    const input = document.getElementById("locationSearchInput");
    const table = document.getElementById("locationTable");
    if (!input || !table) return;

    input.addEventListener("keyup", function () {
      const filter = input.value.toLowerCase();
      const rows = table.querySelectorAll("tbody tr");

      rows.forEach(function (row) {
        const text = row.innerText.toLowerCase();
        row.style.display = text.includes(filter) ? "" : "none";
      });
    });
  })();

  // ---------------------------------------
  // Edit-by-code helpers: fill fields + highlight row
  // ---------------------------------------
  (function setupEditByCodeHelpers() {
    const table = document.getElementById("locationTable");
    const codeInput = document.querySelector('input[data-role="edit-location-code"]');
    const nameInput = document.querySelector('input[data-role="edit-location-name"]');
    const addrInput = document.querySelector('input[data-role="edit-location-address"]');

    if (!table || !codeInput || !nameInput || !addrInput) return;

    function highlightRow(row) {
      const rows = table.querySelectorAll("tbody tr");
      rows.forEach(r => r.classList.remove("table-primary"));
      if (row) {
        row.classList.add("table-primary");
        row.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }

    function fillFromCode() {
      const code = codeInput.value.trim().toUpperCase();
      if (!code) {
        nameInput.value = "";
        addrInput.value = "";
        highlightRow(null);
        return;
      }

      const row = table.querySelector(`tbody tr[data-code="${code}"]`);
      if (row) {
        const name = row.getAttribute("data-name") || "";
        const address = row.getAttribute("data-address") || "";

        nameInput.value = name;
        addrInput.value = address;
        highlightRow(row);
      } else {
        // No matching row among the first 200
        nameInput.value = "";
        addrInput.value = "";
        highlightRow(null);
      }
    }

    codeInput.addEventListener("change", fillFromCode);
    codeInput.addEventListener("blur", fillFromCode);
  })();

});
