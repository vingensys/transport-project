// static/js/booking.js

document.documentElement.setAttribute("data-bookingjs-loaded", "1");

if (window.__BOOKING_JS_INITED__) {
  // Already initialised; prevent double-binding if script is included twice.
} else {
  window.__BOOKING_JS_INITED__ = true;

  document.addEventListener("DOMContentLoaded", function () {
    const BOOKING_AUTH_BY_CODE = window.BOOKING_AUTH_BY_CODE || {};
    const MATERIALS_URL_TEMPLATE =
      window.FLASK_BOOKING_MATERIALS_URL_TEMPLATE || null;

    // Remove unintended required constraints if any
    document.querySelectorAll('select[name="material_mode"]').forEach((el) => {
      el.removeAttribute("required");
    });

    // ---------------------------------------
    // KM suggestions (Home Depot assistant)
    // ---------------------------------------
    const tripKmInput = document.querySelector('input[name="trip_km"]');
    let tripKmDatalist = null;

    if (tripKmInput) {
      tripKmDatalist = document.createElement("datalist");
      tripKmDatalist.id = "tripKmSuggestions";
      document.body.appendChild(tripKmDatalist);
      tripKmInput.setAttribute("list", "tripKmSuggestions");
    }

    function setKmSuggestions(options) {
      if (!tripKmDatalist) return;
      tripKmDatalist.innerHTML = "";

      (options || []).forEach((opt) => {
        if (!opt || opt.km == null) return;
        const o = document.createElement("option");
        o.value = opt.km;
        const parts = [`${opt.km} km`];
        if (opt.route_name) parts.push(opt.route_name);
        o.label = parts.join(" – ");
        tripKmDatalist.appendChild(o);
      });
    }

    function recomputeHomeKmSuggestions() {
      const kmInput = tripKmInput;
      if (!kmInput) return setKmSuggestions([]);

      const homeConfigEl = document.getElementById("bookingHomeConfig");
      if (!homeConfigEl) return setKmSuggestions([]);

      const homeCode = (homeConfigEl.dataset.homeCode || "").toUpperCase();
      const homeDisplay = homeConfigEl.dataset.homeDisplay || "";
      if (!homeCode || !homeDisplay) return setKmSuggestions([]);

      const homeYes = document.getElementById("homeBookingYes");
      if (!homeYes || !homeYes.checked) return setKmSuggestions([]);

      const fromList = document.getElementById("fromBookingLocationList");
      const destList = document.getElementById("destBookingLocationList");
      if (!fromList || !destList) return setKmSuggestions([]);

      const fromItems = Array.from(fromList.querySelectorAll("li[data-code]")).map(
        (li) => li.dataset.code
      );
      const destItems = Array.from(destList.querySelectorAll("li[data-code]")).map(
        (li) => li.dataset.code
      );

      let remote = null;

      if (fromItems.includes(homeCode) && destItems.length === 1) {
        remote = destItems[0];
      } else if (destItems.includes(homeCode) && fromItems.length === 1) {
        remote = fromItems[0];
      }

      if (!remote) return setKmSuggestions([]);

      const url =
        "/admin/route-km-json?from=" +
        encodeURIComponent(homeCode) +
        "&to=" +
        encodeURIComponent(remote);

      fetch(url)
        .then((resp) => resp.json())
        .then((data) => {
          const options = (data && data.options) || [];
          setKmSuggestions(options);

          if (options.length === 1 && options[0].km != null) {
            kmInput.value = options[0].km;
            kmInput.classList.add("border", "border-success");
            setTimeout(() => kmInput.classList.remove("border", "border-success"), 2000);
          }
        })
        .catch(() => setKmSuggestions([]));
    }

    // ---------------------------------------
    // General helpers
    // ---------------------------------------
    function extractCode(raw) {
      if (!raw) return "";
      raw = raw.trim();
      const start = raw.indexOf("[");
      const end = raw.indexOf("]");
      if (start !== -1 && end !== -1 && end > start + 1) {
        return raw.substring(start + 1, end).trim();
      }
      return raw;
    }

    function setupBookingPanel(prefix, listId, hiddenName, role) {
      const input = document.querySelector(`input[data-role="${prefix}-input"]`);
      const button = document.querySelector(`button[data-role="${prefix}-add"]`);
      const list = document.getElementById(listId);
      if (!input || !button || !list) return;

      function addItem() {
        const raw = input.value;
        if (!raw || !raw.trim()) return;

        const code = extractCode(raw).toUpperCase();
        if (!code) return;

        const li = document.createElement("li");
        li.className = "list-group-item d-flex flex-column";
        li.dataset.code = code;
        li.dataset.side = role; // LOADING / UNLOADING

        const topRow = document.createElement("div");
        topRow.className = "d-flex justify-content-between align-items-center";

        const labelSpan = document.createElement("span");
        labelSpan.textContent = raw.trim();
        topRow.appendChild(labelSpan);

        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = hiddenName;
        hidden.value = code;
        topRow.appendChild(hidden);

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "btn btn-sm btn-link text-danger ms-2";
        removeBtn.textContent = "×";
        removeBtn.addEventListener("click", function () {
          li.remove();
          recomputeHomeKmSuggestions();
          scheduleScopesRebuild(); // scopes changed
        });
        topRow.appendChild(removeBtn);

        li.appendChild(topRow);

        const pickBtn = document.createElement("button");
        pickBtn.type = "button";
        pickBtn.className = "btn btn-sm btn-outline-primary mt-2";
        pickBtn.textContent = "Select Authorities";
        pickBtn.dataset.role = "open-authority-picker";
        pickBtn.dataset.code = code;
        pickBtn.dataset.side = role;
        li.appendChild(pickBtn);

        const summaryDiv = document.createElement("div");
        summaryDiv.className = "small mt-1 text-muted";
        summaryDiv.dataset.role = "authority-summary";
        summaryDiv.textContent = "None selected";
        li.appendChild(summaryDiv);

        const selectedContainer = document.createElement("div");
        selectedContainer.dataset.role = "selected-authorities";
        li.appendChild(selectedContainer);

        list.appendChild(li);
        input.value = "";
        input.focus();

        recomputeHomeKmSuggestions();
        scheduleScopesRebuild(); // scopes changed
      }

      button.addEventListener("click", addItem);
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          addItem();
        }
      });
    }

    setupBookingPanel("from-booking", "fromBookingLocationList", "from_locations[]", "LOADING");
    setupBookingPanel("dest-booking", "destBookingLocationList", "dest_locations[]", "UNLOADING");

    // ---------------------------------------
    // Home depot helper (UI only)
    // ---------------------------------------
    (function setupHomeDepotHelper() {
      const homeConfigEl = document.getElementById("bookingHomeConfig");
      if (!homeConfigEl) return;

      const homeCode = (homeConfigEl.dataset.homeCode || "").toUpperCase();
      const homeDisplay = homeConfigEl.dataset.homeDisplay || "";
      const homeAuthorityId = homeConfigEl.dataset.homeAuthorityId || "";

      const fromInput = document.querySelector('[data-role="from-booking-input"]');
      const fromAddBtn = document.querySelector('[data-role="from-booking-add"]');
      const fromList = document.getElementById("fromBookingLocationList");

      const destInput = document.querySelector('[data-role="dest-booking-input"]');
      const destAddBtn = document.querySelector('[data-role="dest-booking-add"]');
      const destList = document.getElementById("destBookingLocationList");

      const directionCol = document.getElementById("homeDirectionCol");

      function listHasCode(list, code) {
        if (!list || !code) return false;
        return !!list.querySelector('li[data-code="' + code + '"]');
      }

      function removeCodeFromList(list, code) {
        if (!list || !code) return;
        list.querySelectorAll('li[data-code="' + code + '"]').forEach((li) => li.remove());
      }

      function addHomeTo(listType) {
        if (!homeCode || !homeDisplay) return;

        let input, addBtn, list, side;
        if (listType === "FROM") {
          if (!fromInput || !fromAddBtn || !fromList) return;
          if (listHasCode(fromList, homeCode)) return;
          input = fromInput;
          addBtn = fromAddBtn;
          list = fromList;
          side = "LOADING";
        } else if (listType === "DEST") {
          if (!destInput || !destAddBtn || !destList) return;
          if (listHasCode(destList, homeCode)) return;
          input = destInput;
          addBtn = destAddBtn;
          list = destList;
          side = "UNLOADING";
        } else return;

        input.value = homeDisplay;
        addBtn.click();

        if (!homeAuthorityId) return;

        const li = list.querySelector('li[data-code="' + homeCode + '"]');
        if (!li) return;

        const selectedContainer = li.querySelector("[data-role='selected-authorities']");
        const summaryDiv = li.querySelector("[data-role='authority-summary']");
        if (!selectedContainer || !summaryDiv) return;

        selectedContainer.innerHTML = "";

        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.value = homeAuthorityId;
        hidden.name = side === "LOADING" ? `loading_${homeCode}[]` : `unloading_${homeCode}[]`;
        selectedContainer.appendChild(hidden);

        const listForCode = BOOKING_AUTH_BY_CODE[homeCode] || [];
        const authNumericId = parseInt(homeAuthorityId, 10);
        const match = listForCode.find((a) => Number(a.id) === authNumericId);

        summaryDiv.textContent = match ? match.title : "Default home authority";
      }

      function syncHomeLocation() {
        const homeYes = document.getElementById("homeBookingYes");
        const homeNo = document.getElementById("homeBookingNo");
        const inboundRadio = document.getElementById("homeInbound");
        const outwardRadio = document.getElementById("homeOutward");

        const isHome = homeYes && homeYes.checked && (!homeNo || !homeNo.checked);

        if (directionCol) directionCol.classList.toggle("d-none", !isHome);

        if (!isHome) {
          removeCodeFromList(fromList, homeCode);
          removeCodeFromList(destList, homeCode);
          setKmSuggestions([]);
          recomputeHomeKmSuggestions();
          scheduleScopesRebuild(); // scopes changed
          return;
        }

        const inboundSelected = inboundRadio && inboundRadio.checked;
        const outwardSelected = outwardRadio && outwardRadio.checked;

        removeCodeFromList(fromList, homeCode);
        removeCodeFromList(destList, homeCode);

        if (inboundSelected) addHomeTo("DEST");
        else if (outwardSelected) addHomeTo("FROM");

        recomputeHomeKmSuggestions();
        scheduleScopesRebuild(); // scopes changed
      }

      ["homeBookingYes", "homeBookingNo", "homeInbound", "homeOutward"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("change", syncHomeLocation);
      });

      syncHomeLocation();
    })();

   // ========================================
// Authority Picker Modal Logic (DROP-IN)
// ========================================
const modalEl = document.getElementById("authorityPickerModal");
const authorityModal = modalEl ? new bootstrap.Modal(modalEl) : null;

let currentLi = null;

function getSelectedAuthorityIds(currentLi) {
  const selectedContainer = currentLi.querySelector("[data-role='selected-authorities']");
  if (!selectedContainer) return [];
  return Array.from(selectedContainer.querySelectorAll("input[type='hidden']")).map((h) => h.value);
}

function renderAuthorityPickerList({ code, side, existingIds }) {
  const authListDiv = document.getElementById("authorityPickerList");
  const emptyDiv = document.getElementById("authorityPickerEmpty");
  if (!authListDiv || !emptyDiv) return;

  authListDiv.innerHTML = "";

  const list = BOOKING_AUTH_BY_CODE[code] || [];

  if (!list.length) {
    emptyDiv.classList.remove("d-none");
    return;
  }

  emptyDiv.classList.add("d-none");

  list.forEach(function (a) {
    const checkWrapper = document.createElement("div");
    checkWrapper.className = "form-check";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "form-check-input";
    cb.id = `auth-${side}-${code}-${a.id}`;
    cb.dataset.authId = a.id;

    if (existingIds.includes(String(a.id))) cb.checked = true;

    const label = document.createElement("label");
    label.className = "form-check-label ms-2";
    label.setAttribute("for", cb.id);
    label.textContent = a.title;

    checkWrapper.appendChild(cb);
    checkWrapper.appendChild(label);
    authListDiv.appendChild(checkWrapper);
  });
}

document.addEventListener("click", function (e) {
  const btn = e.target.closest("button[data-role='open-authority-picker']");
  if (!btn) return;
  if (!authorityModal) return;

  const code = btn.dataset.code;
  const side = btn.dataset.side;
  currentLi = btn.closest("li");

  if (!currentLi) return;

  const existingIds = getSelectedAuthorityIds(currentLi);

  // Clear status + inputs each time modal opens (optional but nice)
  const statusEl = document.getElementById("newAuthorityStatus");
  const titleEl = document.getElementById("newAuthorityTitle");
  const addrEl = document.getElementById("newAuthorityAddress");
  if (statusEl) statusEl.textContent = "";
  if (titleEl) titleEl.value = "";
  if (addrEl) addrEl.value = "";

  renderAuthorityPickerList({ code, side, existingIds });

  authorityModal.show();
});

const applyBtn = document.getElementById("applyAuthoritySelection");
if (applyBtn) {
  applyBtn.addEventListener("click", function () {
    if (!currentLi) return;

    const side = currentLi.dataset.side;
    const code = currentLi.dataset.code;

    const container = currentLi.querySelector("[data-role='selected-authorities']");
    if (!container) return;

    container.innerHTML = "";

    const selectedTitles = [];

    document
      .querySelectorAll("#authorityPickerList input[type='checkbox']")
      .forEach(function (cb) {
        if (cb.checked) {
          const hidden = document.createElement("input");
          hidden.type = "hidden";
          hidden.value = cb.dataset.authId;
          hidden.name = side === "LOADING" ? `loading_${code}[]` : `unloading_${code}[]`;
          container.appendChild(hidden);

          const label = cb.closest(".form-check")?.querySelector(".form-check-label");
          if (label) selectedTitles.push(label.textContent.trim());
        }
      });

    const summaryDiv = currentLi.querySelector("[data-role='authority-summary']");
    if (summaryDiv) summaryDiv.textContent = selectedTitles.length ? selectedTitles.join(", ") : "None selected";

    authorityModal.hide();

    scheduleScopesRebuild(); // scopes changed
  });
}

// ========================================
// Add new authority inside picker modal (COMPLETE REPLACEMENT)
// ========================================
const btnAddAuthority = document.getElementById("btnAddAuthority");
if (btnAddAuthority) {
  btnAddAuthority.addEventListener("click", async function () {
    const statusEl = document.getElementById("newAuthorityStatus");
    const titleEl = document.getElementById("newAuthorityTitle");
    const addrEl = document.getElementById("newAuthorityAddress");

    if (!currentLi) return;

    const code = (currentLi.dataset.code || "").trim().toUpperCase();
    const side = currentLi.dataset.side;

    const title = (titleEl?.value || "").trim();
    const address = (addrEl?.value || "").trim();

    if (!title) {
      if (statusEl) statusEl.textContent = "Designation is required.";
      return;
    }

    const url = window.FLASK_QUICK_ADD_AUTHORITY_URL;
    if (!url) {
      console.error("Missing window.FLASK_QUICK_ADD_AUTHORITY_URL bridge from template.");
      if (statusEl) statusEl.textContent = "Internal error: add-authority URL not configured.";
      return;
    }

    btnAddAuthority.disabled = true;
    if (statusEl) statusEl.textContent = "Adding...";

    try {
      const payload = {
        location_code: code,
        title: title,
        address: address || "",
      };

      const resp = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": window.CSRF_TOKEN,
          "X-CSRF-Token": window.CSRF_TOKEN,
        },
        body: JSON.stringify(payload),
      });

      const data = await resp.json().catch(() => null);

      if (!resp.ok || !data || !data.success) {
        const msg = (data && data.error) || `Failed (${resp.status})`;
        if (statusEl) statusEl.textContent = msg;
        return;
      }

      const a = data.authority; // { id, title, location_code }
      if (!a || !a.id) {
        if (statusEl) statusEl.textContent = "Unexpected response from server.";
        return;
      }

      // Update global cache used by picker
      if (!BOOKING_AUTH_BY_CODE[code]) BOOKING_AUTH_BY_CODE[code] = [];
      BOOKING_AUTH_BY_CODE[code].push({ id: a.id, title: a.title });

      // Re-render list, keeping existing selections + auto-select new one
      const existingIds = getSelectedAuthorityIds(currentLi);
      existingIds.push(String(a.id));

      renderAuthorityPickerList({ code, side, existingIds });

      // Clear inputs + status
      if (titleEl) titleEl.value = "";
      if (addrEl) addrEl.value = "";
      if (statusEl) statusEl.textContent = "Added (selected).";
    } catch (err) {
      console.error(err);
      if (statusEl) statusEl.textContent = "Error while adding authority.";
    } finally {
      btnAddAuthority.disabled = false;
    }
  });
}



    // ========================================
    // Booking Details Modal (with materials) - UPDATED for multi-scope
    // ========================================
    (function setupBookingDetailsModal() {
      const detailModalEl = document.getElementById("bookingDetailModal");
      if (!detailModalEl) return;

      const materialsBody = document.getElementById("bookingDetailMaterialsBody");
      const materialsSummaryEl = document.getElementById("bookingDetailMaterialsSummary");

      function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value || "";
      }

      function renderMaterialsPlaceholder(message) {
        if (!materialsBody) return;
        materialsBody.innerHTML =
          '<tr class="text-muted"><td colspan="6">' + message + "</td></tr>";
        if (materialsSummaryEl) materialsSummaryEl.textContent = "";
      }

      function td(text, align) {
        const cell = document.createElement("td");
        if (align) cell.classList.add("text-" + align);
        cell.textContent = text === null || text === undefined ? "" : String(text);
        return cell;
      }

      function renderLegacyMaterials(data) {
        // Legacy shape: {success, has_materials, mode, header, lines}
        if (!data || data.success === false || !data.has_materials) {
          renderMaterialsPlaceholder("No material details available.");
          return;
        }

        const lines = data.lines || [];
        const mode = (data.mode || "").toUpperCase();
        const header = data.header || {};

        if (!lines.length) {
          renderMaterialsPlaceholder("No material details available.");
          return;
        }

        materialsBody.innerHTML = "";
        lines.forEach((line, idx) => {
          const tr = document.createElement("tr");
          const sl = line.sequence_index || idx + 1;
          tr.appendChild(td(sl, "center"));
          tr.appendChild(td(line.description || "", null));
          tr.appendChild(td(line.unit || "", "center"));
          tr.appendChild(
            td(line.quantity != null && line.quantity !== "" ? line.quantity : "", "end")
          );
          tr.appendChild(
            td(line.rate != null && line.rate !== "" ? line.rate : "", "end")
          );
          tr.appendChild(
            td(line.amount != null && line.amount !== "" ? line.amount : "", "end")
          );
          materialsBody.appendChild(tr);
        });

        if (!materialsSummaryEl) return;

        const qtyHeader = header.total_quantity;
        const unitHeader = header.total_quantity_unit;
        const amtHeader = header.total_amount;

        let anyLineQty = false;
        lines.forEach((line) => {
          const q = line.quantity;
          if (
            q !== null &&
            q !== undefined &&
            q !== "" &&
            !isNaN(parseFloat(q)) &&
            parseFloat(q) > 0
          ) {
            anyLineQty = true;
          }
        });

        if (mode === "ITEM") {
          materialsSummaryEl.textContent =
            amtHeader != null && amtHeader !== ""
              ? "Item-wise materials. Total amount: ₹ " + amtHeader
              : "Item-wise materials.";
        } else if (mode === "LUMPSUM") {
          let parts = ["Lumpsum materials"];
          if (!anyLineQty) {
            if (qtyHeader != null && qtyHeader !== "") {
              parts.push(
                "Total quantity: " + qtyHeader + (unitHeader ? " " + unitHeader : "")
              );
            } else if (unitHeader) {
              parts.push("Unit: " + unitHeader);
            }
          }
          if (amtHeader != null && amtHeader !== "") parts.push("Total amount: ₹ " + amtHeader);
          materialsSummaryEl.textContent = parts.join(" · ");
        } else if (mode === "ATTACHED") {
          materialsSummaryEl.textContent =
            amtHeader != null && amtHeader !== ""
              ? "Attached materials. Total amount: ₹ " + amtHeader
              : "Attached materials.";
        } else {
          materialsSummaryEl.textContent = "";
        }
      }

      function isMultiScopePayload(data) {
        // Multi-scope shape: {success, booking_id, booking_level, loading, unloading, from_to}
        return (
          data &&
          data.success !== false &&
          (Array.isArray(data.from_to) ||
            Array.isArray(data.loading) ||
            Array.isArray(data.unloading) ||
            Array.isArray(data.booking_level))
        );
      }

      function renderMultiScopeMaterials(data) {
        const fromTo = Array.isArray(data.from_to) ? data.from_to : [];
        const bookingLevel = Array.isArray(data.booking_level) ? data.booking_level : [];

        // Prefer from_to for a clean “scope” view; if empty, fall back to booking_level
        const scopes = fromTo.length ? fromTo : bookingLevel;

        if (!scopes.length) {
          renderMaterialsPlaceholder("No material details available.");
          return;
        }

        materialsBody.innerHTML = "";

        let scopeCount = 0;

        scopes.forEach((scope) => {
          scopeCount += 1;

          const mode = (scope.mode || "").toUpperCase();
          const header = scope.header || {};
          const lines = scope.lines || [];

          const fromTitle =
            scope.from_authority?.title ||
            scope.authority?.title ||
            scope.from_authority?.authority_title ||
            "Loading";
          const toTitle =
            scope.to_authority?.title ||
            scope.to_authority?.authority_title ||
            "Unloading";

          // Scope header row (colspan)
          const trHead = document.createElement("tr");
          trHead.classList.add("table-light");
          const headCell = document.createElement("td");
          headCell.colSpan = 6;

          const qtyHeader = header.total_quantity;
          const unitHeader = header.total_quantity_unit;
          const amtHeader = header.total_amount;

          const parts = [];
          if (mode) parts.push(mode);
          if (mode === "LUMPSUM" && qtyHeader != null && qtyHeader !== "") {
            parts.push("Qty: " + qtyHeader + (unitHeader ? " " + unitHeader : ""));
          }
          if (amtHeader != null && amtHeader !== "") parts.push("Amt: ₹ " + amtHeader);

          headCell.innerHTML =
            `<strong>Scope ${scopeCount}:</strong> ` +
            `${fromTitle} <span class="text-muted">→</span> ${toTitle}` +
            (parts.length ? ` <span class="text-muted">·</span> <span class="text-muted">${parts.join(" · ")}</span>` : "");

          trHead.appendChild(headCell);
          materialsBody.appendChild(trHead);

          // Lines
          if (!lines.length) {
            const trEmpty = document.createElement("tr");
            trEmpty.appendChild(td("", "center"));
            trEmpty.appendChild(td("(No lines)", null));
            trEmpty.appendChild(td("", "center"));
            trEmpty.appendChild(td("", "end"));
            trEmpty.appendChild(td("", "end"));
            trEmpty.appendChild(td("", "end"));
            materialsBody.appendChild(trEmpty);
            return;
          }

          lines.forEach((line, idx) => {
            const tr = document.createElement("tr");
            const sl = line.sequence_index || idx + 1;

            tr.appendChild(td(sl, "center"));
            tr.appendChild(td(line.description || "", null));
            tr.appendChild(td(line.unit || "", "center"));
            tr.appendChild(td(line.quantity != null && line.quantity !== "" ? line.quantity : "", "end"));
            tr.appendChild(td(line.rate != null && line.rate !== "" ? line.rate : "", "end"));
            tr.appendChild(td(line.amount != null && line.amount !== "" ? line.amount : "", "end"));

            materialsBody.appendChild(tr);
          });
        });

        if (!materialsSummaryEl) return;
        materialsSummaryEl.textContent = `Materials loaded for ${scopeCount} scope(s).`;
      }

      document.addEventListener("click", function (event) {
        const button = event.target.closest("[data-booking-id]");
        if (!button) return;

        const ds = button.dataset;

        setText("bookingDetailTripSerial", ds.tripSerial);
        setText("bookingDetailBookingId", ds.bookingId);
        setText("bookingDetailBookingDate", ds.bookingDate);
        setText("bookingDetailPlacementDate", ds.placementDate);
        setText("bookingDetailCompany", ds.company);
        setText("bookingDetailLorry", ds.lorry);
        setText("bookingDetailFrom", ds.from);
        setText("bookingDetailDest", ds.dest);
        setText("bookingDetailRoute", ds.route);
        setText("bookingDetailTripKm", ds.tripKm);

        renderMaterialsPlaceholder("Loading materials…");
        const modalInstance = bootstrap.Modal.getOrCreateInstance(detailModalEl);
        modalInstance.show();

        if (!materialsBody || !MATERIALS_URL_TEMPLATE) return;

        const bookingId = ds.bookingId;
        if (!bookingId) {
          renderMaterialsPlaceholder("No material details available.");
          return;
        }

        const url = MATERIALS_URL_TEMPLATE.replace("__ID__", bookingId);

        fetch(url, { headers: { Accept: "application/json" } })
          .then((resp) => {
            if (!resp.ok) throw new Error("Server error " + resp.status);
            return resp.json();
          })
          .then((data) => {
            // Multi-scope?
            if (isMultiScopePayload(data)) {
              renderMultiScopeMaterials(data);
              return;
            }
            // Fallback legacy
            renderLegacyMaterials(data);
          })
          .catch(() => {
            renderMaterialsPlaceholder("Error loading material details from server.");
          });
      });
    })();

    // ========================================
    // Multi-scope Materials UI (corrected)
    // ========================================
    (function setupMaterialsScopesMultiUI() {
      const accordion = document.getElementById("materialsScopesAccordion");
      const scopesJsonInput = document.getElementById("materialsScopesJSON");
      const errorEl = document.getElementById("materialsScopesError");
      const emptyHintEl = document.getElementById("materialsScopesEmptyHint");
      const saveBtn = document.getElementById("btnSaveBooking");

      if (!accordion || !scopesJsonInput) return;

      function q(sel, root) {
        return (root || document).querySelector(sel);
      }
      function qa(sel, root) {
        return Array.from((root || document).querySelectorAll(sel));
      }
      function esc(s) {
        return String(s || "").replace(/[&<>"']/g, (c) => ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }[c]));
      }

      function setEmptyHintVisible(isVisible) {
        if (!emptyHintEl) return;
        emptyHintEl.classList.toggle("d-none", !isVisible);
      }

      function setSaveEnabled(isEnabled) {
        if (!saveBtn) return;
        saveBtn.disabled = !isEnabled;
      }

      function parseNum(v) {
        if (v == null) return null;
        const s = String(v).trim();
        if (!s) return null;
        const n = Number(s);
        return Number.isFinite(n) ? n : null;
      }

      function getSelectedAuthorities(side) {
        const listId = side === "LOADING" ? "fromBookingLocationList" : "destBookingLocationList";
        const list = document.getElementById(listId);
        if (!list) return [];

        const items = qa("li[data-code]", list);
        const out = [];

        items.forEach((li) => {
          const code = (li.dataset.code || "").toUpperCase();
          const container = q("[data-role='selected-authorities']", li);
          const ids = container ? qa("input[type='hidden']", container).map((h) => String(h.value)) : [];
          ids.forEach((id) => out.push({ location_code: code, authority_id: id }));
        });

        return out;
      }

      function computeAuthorityPairScopes() {
        const loading = getSelectedAuthorities("LOADING");
        const unloading = getSelectedAuthorities("UNLOADING");

        const scopes = [];
        loading.forEach((l) => {
          unloading.forEach((u) => {
            scopes.push({
              from: { location_code: l.location_code, authority_id: l.authority_id },
              to: { location_code: u.location_code, authority_id: u.authority_id },
              material: null,
            });
          });
        });
        return scopes;
      }

      function findAuthorityTitle(locationCode, authorityId) {
        const list = BOOKING_AUTH_BY_CODE[(locationCode || "").toUpperCase()] || [];
        const idNum = Number(authorityId);
        const match = list.find((a) => Number(a.id) === idNum);
        return match ? match.title : `Authority #${authorityId}`;
      }

      function scopeHeaderText(scope) {
        const fCode = (scope.from.location_code || "").toUpperCase();
        const tCode = (scope.to.location_code || "").toUpperCase();
        const fTitle = findAuthorityTitle(fCode, scope.from.authority_id);
        const tTitle = findAuthorityTitle(tCode, scope.to.authority_id);
        return `${fCode} (${fTitle}) \u2192 ${tCode} (${tTitle})`;
      }

      function setScopesJson(scopes) {
        scopesJsonInput.value = JSON.stringify({
          mode: "AUTHORITY_PAIR",
          scopes: scopes,
        });
      }

      // ---- Validation rules ----
      function validateMaterialBlock(block) {
        if (!block) return { ok: false, msg: "Material block missing." };

        const mode = (block.mode || "").toUpperCase();
        if (!["ITEM", "LUMPSUM", "ATTACHED"].includes(mode)) {
          return { ok: false, msg: "Select a material mode." };
        }

        const lines = Array.isArray(block.lines) ? block.lines : [];

        if (mode === "ATTACHED") {
          const amt = parseNum(block.total_amount);
          if (amt == null) return { ok: false, msg: "ATTACHED: Total Amount is required." };
          return { ok: true };
        }

        if (mode === "ITEM") {
          const hasComputed = lines.some((ln) => parseNum(ln.amount) != null);
          if (!hasComputed) return { ok: false, msg: "ITEM: add at least one row with Qty + Rate." };
          return { ok: true };
        }

        // LUMPSUM
        const headerQty = parseNum(block.total_quantity);
        const anyLineQty = lines.some((ln) => parseNum(ln.quantity) != null && parseNum(ln.quantity) !== 0);
        if (headerQty != null && anyLineQty) {
          return { ok: false, msg: "LUMPSUM: use either header quantity OR line quantities, not both." };
        }

        const hasSomething =
          headerQty != null ||
          parseNum(block.total_amount) != null ||
          String(block.total_quantity_unit || "").trim().length > 0 ||
          lines.some((ln) => String(ln.description || "").trim().length > 0);

        if (!hasSomething) {
          return { ok: false, msg: "LUMPSUM: enter header Qty/Amount (or) at least one line." };
        }

        return { ok: true };
      }

      function computeValidity(scopesWithBlocks) {
        if (!Array.isArray(scopesWithBlocks) || scopesWithBlocks.length === 0) {
          return { ok: false, msg: "Please add at least one FROM → TO authority scope." };
        }
        for (let i = 0; i < scopesWithBlocks.length; i++) {
          const v = validateMaterialBlock(scopesWithBlocks[i].material);
          if (!v.ok) return { ok: false, msg: `Scope #${i + 1}: ${v.msg}` };
        }
        return { ok: true };
      }

      // ---------- Materials table builder ----------
      function createMaterialsTableDOM(scopeIndex, onAnyChange) {
        const uid = `S${scopeIndex}`;

        const wrap = document.createElement("div");
        wrap.dataset.role = "scope-material-root";
        wrap.dataset.scopeIndex = String(scopeIndex);

        wrap.innerHTML = `
          <div class="row g-2 align-items-end mb-2">
            <div class="col-md-3">
              <label class="form-label form-label-sm mb-1">Mode</label>
              <select class="form-select form-select-sm" id="material_mode_${uid}">
                <option value="">-- Select --</option>
                <option value="ITEM">ITEM</option>
                <option value="LUMPSUM">LUMPSUM</option>
                <option value="ATTACHED">ATTACHED</option>
              </select>
            </div>
          </div>

          <div class="table-responsive">
            <table class="table table-sm table-bordered align-middle mb-2">
              <thead class="table-light">
                <tr>
                  <th style="width:5%;">#</th>
                  <th>Description</th>
                  <th style="width:12%;" data-col="unit">Unit</th>
                  <th style="width:12%;" data-col="qty">Qty</th>
                  <th style="width:12%;" data-col="rate">Rate</th>
                  <th style="width:12%;" data-col="amt">Amount</th>
                  <th style="width:6%;" data-col="rm"></th>
                </tr>
              </thead>
              <tbody id="materialLinesBody_${uid}"></tbody>
            </table>
          </div>

          <div class="row g-2 align-items-end mt-2">
            <div class="col-md-3" id="materialTotalQtyGroup_${uid}" style="display:none;">
              <label class="form-label form-label-sm mb-1">Total Quantity</label>
              <input type="number" step="0.01" min="0" class="form-control form-control-sm"
                id="material_total_quantity_${uid}">
            </div>

            <div class="col-md-2" id="materialTotalQtyUnitGroup_${uid}" style="display:none;">
              <label class="form-label form-label-sm mb-1">Unit</label>
              <input type="text" class="form-control form-control-sm"
                id="material_total_quantity_unit_${uid}">
            </div>

            <div class="col-md-4" id="materialTotalAmtGroup_${uid}">
              <label class="form-label form-label-sm mb-1">Total Amount</label>
              <input type="number" step="0.01" min="0" class="form-control form-control-sm"
                id="material_total_amount_${uid}">
            </div>
          </div>

          <div class="d-flex justify-content-between align-items-center mt-3">
            <button type="button" class="btn btn-sm btn-outline-secondary" id="btnAddMaterialRow_${uid}">
              + Add row
            </button>
            <span class="small text-muted">Scope materials</span>
          </div>
        `;

        const modeSel = wrap.querySelector(`#material_mode_${uid}`);
        const tbody = wrap.querySelector(`#materialLinesBody_${uid}`);
        const addBtn = wrap.querySelector(`#btnAddMaterialRow_${uid}`);

        const qtyGroup = wrap.querySelector(`#materialTotalQtyGroup_${uid}`);
        const unitGroup = wrap.querySelector(`#materialTotalQtyUnitGroup_${uid}`);
        const qtyInput = wrap.querySelector(`#material_total_quantity_${uid}`);
        const unitInput = wrap.querySelector(`#material_total_quantity_unit_${uid}`);
        const amtInput = wrap.querySelector(`#material_total_amount_${uid}`);

        function createRow(opts) {
          const o = opts || {};
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td class="text-center" data-role="sl"></td>
            <td><input type="text" class="form-control form-control-sm" placeholder="Description" value="${esc(o.desc || "")}"></td>
            <td data-col="unit"><input type="text" class="form-control form-control-sm" placeholder="Unit" value="${esc(o.unit || "")}"></td>
            <td data-col="qty"><input type="number" step="0.01" min="0" class="form-control form-control-sm" placeholder="Qty" value="${o.qty != null ? esc(o.qty) : ""}"></td>
            <td data-col="rate"><input type="number" step="0.01" min="0" class="form-control form-control-sm" placeholder="Rate" value="${o.rate != null ? esc(o.rate) : ""}"></td>
            <td data-col="amt"><input type="number" step="0.01" min="0" class="form-control form-control-sm" placeholder="Amount" value="${o.amt != null ? esc(o.amt) : ""}"></td>
            <td class="text-center" data-col="rm"><button type="button" class="btn btn-sm btn-outline-danger" data-role="rm">×</button></td>
          `;
          return tr;
        }

        function renumberRows() {
          Array.from(tbody.querySelectorAll("tr")).forEach((tr, idx) => {
            const cell = tr.querySelector("[data-role='sl']");
            if (cell) cell.textContent = String(idx + 1);
          });
        }

        function ensureOneRow() {
          if (!tbody.querySelector("tr")) tbody.appendChild(createRow());
          renumberRows();
        }

        function setAttachedRow() {
          tbody.innerHTML = "";
          const tr = createRow({ desc: "As per list attached." });
          tbody.appendChild(tr);
          renumberRows();
          tr.querySelectorAll("input").forEach((inp) => inp.setAttribute("disabled", "disabled"));
        }

        function resetIfAttachedPlaceholder() {
          const onlyRow = tbody.querySelector("tr");
          if (!onlyRow) return;
          const desc = onlyRow.querySelector("td input[type='text']");
          if (!desc) return;
          const isAttached =
            desc.disabled &&
            (desc.value || "").trim().toLowerCase() === "as per list attached.";
          if (isAttached) {
            tbody.innerHTML = "";
            tbody.appendChild(createRow());
            renumberRows();
          }
        }

        function updateLumpsumLocks() {
          const mode = modeSel.value || "";
          if (mode !== "LUMPSUM") return;

          let anyLineQty = false;
          tbody.querySelectorAll("tr").forEach((tr) => {
            const qty = tr.querySelector("td[data-col='qty'] input");
            const v = qty ? parseNum(qty.value) : null;
            if (v != null && v !== 0) anyLineQty = true;
          });

          const headerQty = parseNum(qtyInput.value);
          const headerHasQty = headerQty != null && headerQty !== 0;

          if (anyLineQty) {
            qtyInput.disabled = true;
            unitInput.disabled = true;
            tbody.querySelectorAll("td[data-col='qty'] input").forEach((inp) => (inp.disabled = false));
          } else if (headerHasQty) {
            qtyInput.disabled = false;
            unitInput.disabled = false;
            tbody.querySelectorAll("td[data-col='qty'] input").forEach((inp) => {
              inp.value = "";
              inp.disabled = true;
            });
          } else {
            qtyInput.disabled = false;
            unitInput.disabled = false;
            tbody.querySelectorAll("td[data-col='qty'] input").forEach((inp) => (inp.disabled = false));
          }
        }

        function recomputeItemAmounts() {
          const mode = modeSel.value || "";
          if (mode !== "ITEM") return;

          let sum = 0;
          tbody.querySelectorAll("tr").forEach((tr) => {
            const qty = tr.querySelector("td[data-col='qty'] input");
            const rate = tr.querySelector("td[data-col='rate'] input");
            const amt = tr.querySelector("td[data-col='amt'] input");

            const qv = qty ? parseNum(qty.value) : null;
            const rv = rate ? parseNum(rate.value) : null;

            if (amt) {
              if (qv != null && rv != null) {
                const av = qv * rv;
                amt.value = Number.isFinite(av) ? av.toFixed(2) : "";
                sum += Number.isFinite(av) ? av : 0;
              } else {
                amt.value = "";
              }
            }
          });

          amtInput.value = sum > 0 ? sum.toFixed(2) : "";
        }

        function applyModeVisibility() {
          const mode = modeSel.value || "";

          if (mode !== "ATTACHED") resetIfAttachedPlaceholder();

          const showQtyHeader = mode === "LUMPSUM";
          qtyGroup.style.display = showQtyHeader ? "" : "none";
          unitGroup.style.display = showQtyHeader ? "" : "none";

          const showRateAmt = mode === "ITEM";
          const showQtyUnitCols = mode === "ITEM" || mode === "LUMPSUM";
          const showRm = mode !== "ATTACHED";

          wrap.querySelectorAll("[data-col='unit']").forEach((el) => (el.style.display = showQtyUnitCols ? "" : "none"));
          wrap.querySelectorAll("[data-col='qty']").forEach((el) => (el.style.display = showQtyUnitCols ? "" : "none"));
          wrap.querySelectorAll("[data-col='rate']").forEach((el) => (el.style.display = showRateAmt ? "" : "none"));
          wrap.querySelectorAll("[data-col='amt']").forEach((el) => (el.style.display = showRateAmt ? "" : "none"));
          wrap.querySelectorAll("[data-col='rm']").forEach((el) => (el.style.display = showRm ? "" : "none"));

          if (mode === "ITEM") {
            qtyInput.value = "";
            unitInput.value = "";
            qtyInput.disabled = true;
            unitInput.disabled = true;

            amtInput.disabled = true;

            addBtn.disabled = false;

            ensureOneRow();
            tbody.querySelectorAll("tr").forEach((tr) => {
              const unit = tr.querySelector("td[data-col='unit'] input");
              const qty = tr.querySelector("td[data-col='qty'] input");
              const rate = tr.querySelector("td[data-col='rate'] input");
              const amt = tr.querySelector("td[data-col='amt'] input");
              const desc = tr.querySelector("td input[type='text']");

              if (unit) unit.disabled = false;
              if (qty) qty.disabled = false;
              if (rate) rate.disabled = false;
              if (amt) {
                amt.disabled = true;
                amt.setAttribute("readonly", "readonly");
              }
              if (desc) desc.disabled = false;
            });
          } else if (mode === "LUMPSUM") {
            amtInput.disabled = false;
            addBtn.disabled = false;

            ensureOneRow();

            tbody.querySelectorAll("tr").forEach((tr) => {
              const rate = tr.querySelector("td[data-col='rate'] input");
              const amt = tr.querySelector("td[data-col='amt'] input");
              if (rate) {
                rate.value = "";
                rate.disabled = true;
              }
              if (amt) {
                amt.value = "";
                amt.disabled = true;
              }
            });

            updateLumpsumLocks();
          } else if (mode === "ATTACHED") {
            qtyInput.value = "";
            unitInput.value = "";
            qtyInput.disabled = true;
            unitInput.disabled = true;

            amtInput.disabled = false;

            addBtn.disabled = true;
            setAttachedRow();
          } else {
            qtyInput.value = "";
            unitInput.value = "";
            qtyInput.disabled = true;
            unitInput.disabled = true;

            amtInput.disabled = false;

            addBtn.disabled = false;
            ensureOneRow();
          }
        }

        // init
        tbody.appendChild(createRow());
        renumberRows();
        applyModeVisibility();

        // IMPORTANT: these changes DO NOT rebuild accordion; they only trigger onAnyChange()
        addBtn.addEventListener("click", () => {
          if ((modeSel.value || "") === "ATTACHED") return;
          tbody.appendChild(createRow());
          renumberRows();
          applyModeVisibility();
          updateLumpsumLocks();
          recomputeItemAmounts();
          if (onAnyChange) onAnyChange();
        });

        tbody.addEventListener("click", (e) => {
          const rm = e.target.closest("[data-role='rm']");
          if (!rm) return;
          if ((modeSel.value || "") === "ATTACHED") return;

          const tr = rm.closest("tr");
          if (tr) tr.remove();
          ensureOneRow();
          applyModeVisibility();
          updateLumpsumLocks();
          recomputeItemAmounts();
          if (onAnyChange) onAnyChange();
        });

        tbody.addEventListener("input", () => {
          updateLumpsumLocks();
          recomputeItemAmounts();
          if (onAnyChange) onAnyChange();
        });

        qtyInput.addEventListener("input", () => {
          updateLumpsumLocks();
          if (onAnyChange) onAnyChange();
        });

        modeSel.addEventListener("change", () => {
          applyModeVisibility();
          updateLumpsumLocks();
          recomputeItemAmounts();
          if (onAnyChange) onAnyChange();
        });

        function readBlock() {
          const mode = (modeSel.value || "").toUpperCase();

          const lines = [];
          tbody.querySelectorAll("tr").forEach((tr) => {
            const desc = (tr.querySelector("td input[type='text']")?.value || "").trim();
            const unit = (tr.querySelector("td[data-col='unit'] input")?.value || "").trim();
            const qty = parseNum(tr.querySelector("td[data-col='qty'] input")?.value);
            const rate = parseNum(tr.querySelector("td[data-col='rate'] input")?.value);
            const amt = parseNum(tr.querySelector("td[data-col='amt'] input")?.value);

            if (!desc && !unit && qty == null && rate == null && amt == null) return;

            lines.push({
              description: desc,
              unit: unit || null,
              quantity: qty,
              rate: rate,
              amount: amt,
            });
          });

          return {
            mode: mode || null,
            total_quantity: parseNum(qtyInput.value),
            total_quantity_unit: (unitInput.value || "").trim() || null,
            total_amount: parseNum(amtInput.value),
            lines: lines,
          };
        }

        wrap.__readMaterialBlock__ = readBlock;
        return wrap;
      }

      // Current scope list (in memory, regenerated when authorities change)
      let currentScopes = [];
      let lastSignature = "";

      function signatureOfScopes(scopes) {
        return JSON.stringify(
          scopes.map((s) => [
            (s.from.location_code || "").toUpperCase(),
            String(s.from.authority_id),
            (s.to.location_code || "").toUpperCase(),
            String(s.to.authority_id),
          ])
        );
      }

      function collectBlocksIntoCurrentScopes() {
        const items = Array.from(accordion.querySelectorAll(".accordion-item"));
        currentScopes.forEach((scope, idx) => {
          const item = items[idx];
          const root = item ? item.__materialRoot__ : null;
          scope.material = root && root.__readMaterialBlock__ ? root.__readMaterialBlock__() : null;
        });
        return currentScopes;
      }

      function updateJsonAndValidityUI() {
        const scopesWithBlocks = collectBlocksIntoCurrentScopes();
        const validity = computeValidity(scopesWithBlocks);

        setScopesJson(scopesWithBlocks);
        setEmptyHintVisible(scopesWithBlocks.length === 0);
        setSaveEnabled(validity.ok);

        if (errorEl) {
          if (validity.ok) {
            errorEl.classList.add("d-none");
          } else {
            // keep hidden during typing; show on submit only
            errorEl.classList.add("d-none");
          }
        }
      }

      function buildAccordionForScopes(scopes) {
        accordion.innerHTML = "";

        scopes.forEach((scope, idx) => {
          const headId = `matScopeHead_${idx}`;
          const bodyId = `matScopeBody_${idx}`;
          const title = scopeHeaderText(scope);

          const item = document.createElement("div");
          item.className = "accordion-item";
          item.innerHTML = `
            <h2 class="accordion-header" id="${headId}">
              <button class="accordion-button ${idx === 0 ? "" : "collapsed"}" type="button"
                data-bs-toggle="collapse" data-bs-target="#${bodyId}"
                aria-expanded="${idx === 0 ? "true" : "false"}" aria-controls="${bodyId}">
                ${esc(title)}
              </button>
            </h2>
            <div id="${bodyId}" class="accordion-collapse collapse ${idx === 0 ? "show" : ""}"
              aria-labelledby="${headId}">
              <div class="accordion-body" data-role="scope-body"></div>
            </div>
          `;

          const body = item.querySelector("[data-role='scope-body']");
          const tableDom = createMaterialsTableDOM(idx + 1, updateJsonAndValidityUI);
          body.appendChild(tableDom);

          item.__materialRoot__ = tableDom;
          accordion.appendChild(item);
        });
      }

      // Debounced rebuild ONLY for scope changes
      let rebuildTimer = null;
      function scheduleRebuild() {
        if (rebuildTimer) clearTimeout(rebuildTimer);
        rebuildTimer = setTimeout(() => {
          const scopes = computeAuthorityPairScopes();
          const sig = signatureOfScopes(scopes);

          currentScopes = scopes;

          // rebuild accordion only if scopes changed
          if (sig !== lastSignature) {
            lastSignature = sig;
            buildAccordionForScopes(currentScopes);
          }

          updateJsonAndValidityUI();
        }, 60);
      }

      window.__BOOKING_SCHEDULE_SCOPES_REBUILD__ = scheduleRebuild;

      // initial
      scheduleRebuild();

      // submit guard
      const form = accordion.closest("form");
      if (form) {
        form.addEventListener("submit", (e) => {
          updateJsonAndValidityUI();
          const validity = computeValidity(collectBlocksIntoCurrentScopes());
          if (!validity.ok) {
            e.preventDefault();
            if (errorEl) {
              errorEl.textContent = validity.msg || "Please complete all scope material tables.";
              errorEl.classList.remove("d-none");
            }
          }
        });
      }
    })();

    // Global helper called from earlier sections
    function scheduleScopesRebuild() {
      if (window.__BOOKING_SCHEDULE_SCOPES_REBUILD__) {
        window.__BOOKING_SCHEDULE_SCOPES_REBUILD__();
      }
    }
    window.scheduleScopesRebuild = scheduleScopesRebuild;
  });
}
