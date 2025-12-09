// static/js/booking.js

if (window.__BOOKING_JS_INITED__) {
  // Already initialised; prevent double-binding if script is included twice.
} else {
  window.__BOOKING_JS_INITED__ = true;

  document.addEventListener("DOMContentLoaded", function () {
    // This is injected from the template via:
    // window.BOOKING_AUTH_BY_CODE = {{ booking_auth_map|tojson }};
    const BOOKING_AUTH_BY_CODE = window.BOOKING_AUTH_BY_CODE || {};
    const MATERIALS_URL_TEMPLATE =
      window.FLASK_BOOKING_MATERIALS_URL_TEMPLATE || null;

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
        if (opt.route_name) {
          parts.push(opt.route_name);
        }
        o.label = parts.join(" – ");

        tripKmDatalist.appendChild(o);
      });
    }

    // Central KM assistant: inspects current DOM + home settings
    function recomputeHomeKmSuggestions() {
      const kmInput = tripKmInput;
      if (!kmInput) {
        setKmSuggestions([]);
        return;
      }

      const homeConfigEl = document.getElementById("bookingHomeConfig");
      if (!homeConfigEl) {
        setKmSuggestions([]);
        return;
      }

      const homeCode = (homeConfigEl.dataset.homeCode || "").toUpperCase();
      const homeDisplay = homeConfigEl.dataset.homeDisplay || "";

      if (!homeCode || !homeDisplay) {
        setKmSuggestions([]);
        return;
      }

      // Only assist when "Home booking = Yes"
      const homeYes = document.getElementById("homeBookingYes");
      if (!homeYes || !homeYes.checked) {
        setKmSuggestions([]);
        return;
      }

      const fromList = document.getElementById("fromBookingLocationList");
      const destList = document.getElementById("destBookingLocationList");
      if (!fromList || !destList) {
        setKmSuggestions([]);
        return;
      }

      const fromItems = Array.from(
        fromList.querySelectorAll("li[data-code]")
      ).map((li) => li.dataset.code);
      const destItems = Array.from(
        destList.querySelectorAll("li[data-code]")
      ).map((li) => li.dataset.code);

      // Determine the single "remote" station:
      // - Home in FROM + exactly 1 remote in DEST  → remote = DEST[0]
      // - Home in DEST + exactly 1 remote in FROM  → remote = FROM[0]
      let remote = null;

      if (fromItems.includes(homeCode) && destItems.length === 1) {
        remote = destItems[0];
      } else if (destItems.includes(homeCode) && fromItems.length === 1) {
        remote = fromItems[0];
      }

      if (!remote) {
        setKmSuggestions([]);
        return;
      }

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

          // If there is exactly one clear match, auto-fill for convenience
          if (options.length === 1 && options[0].km != null) {
            const km = options[0].km;
            kmInput.value = km;
            kmInput.classList.add("border", "border-success");
            setTimeout(() => {
              kmInput.classList.remove("border", "border-success");
            }, 2000);
          }
          // If multiple options: user will see them as dropdown suggestions
          // and pick one; we don't overwrite their input.
        })
        .catch(() => {
          // On error, just clear suggestions; user can type manually.
          setKmSuggestions([]);
        });
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
      return raw; // fallback: user typed pure code
    }

    function setupBookingPanel(prefix, listId, hiddenName, role) {
      const input = document.querySelector(`input[data-role="${prefix}-input"]`);
      const button = document.querySelector(
        `button[data-role="${prefix}-add"]`
      );
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

        // Top row: label + hidden code + remove button
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
          // FROM/DEST changed → recompute suggestions
          recomputeHomeKmSuggestions();
        });
        topRow.appendChild(removeBtn);

        li.appendChild(topRow);

        // Authority picker button
        const pickBtn = document.createElement("button");
        pickBtn.type = "button";
        pickBtn.className = "btn btn-sm btn-outline-primary mt-2";
        pickBtn.textContent = "Select Authorities";
        pickBtn.dataset.role = "open-authority-picker";
        pickBtn.dataset.code = code;
        pickBtn.dataset.side = role; // LOADING / UNLOADING
        li.appendChild(pickBtn);

        // Summary display
        const summaryDiv = document.createElement("div");
        summaryDiv.className = "small mt-1 text-muted";
        summaryDiv.dataset.role = "authority-summary";
        summaryDiv.textContent = "None selected";
        li.appendChild(summaryDiv);

        // Hidden container for selected authority IDs
        const selectedContainer = document.createElement("div");
        selectedContainer.dataset.role = "selected-authorities";
        li.appendChild(selectedContainer);

        list.appendChild(li);
        input.value = "";
        input.focus();

        // FROM/DEST changed → recompute suggestions
        recomputeHomeKmSuggestions();
      }

      button.addEventListener("click", addItem);
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          addItem();
        }
      });
    }

    // FROM side: will submit as from_locations[] and loading_XXX[]
    setupBookingPanel(
      "from-booking",
      "fromBookingLocationList",
      "from_locations[]",
      "LOADING"
    );

    // DEST side: will submit as dest_locations[] and unloading_XXX[]
    setupBookingPanel(
      "dest-booking",
      "destBookingLocationList",
      "dest_locations[]",
      "UNLOADING"
    );

    // Re-evaluate KM suggestions when FROM / DEST lists change manually
    document.addEventListener("click", function (e) {
      if (
        e.target.matches('[data-role="from-booking-add"]') ||
        e.target.matches('[data-role="dest-booking-add"]')
      ) {
        setTimeout(() => {
          const homeYes = document.getElementById("homeBookingYes");
          if (homeYes && homeYes.checked) {
            recomputeHomeKmSuggestions();
          }
        }, 200);
      }

      if (e.target.closest("button.btn-link.text-danger")) {
        setTimeout(() => {
          recomputeHomeKmSuggestions();
        }, 200);
      }
    });

    // ========================================
    // Home depot helper (UI only)
    // ========================================
    (function setupHomeDepotHelper() {
      const homeConfigEl = document.getElementById("bookingHomeConfig");
      if (!homeConfigEl) {
        return;
      }

      const homeCode = (homeConfigEl.dataset.homeCode || "").toUpperCase();
      const homeDisplay = homeConfigEl.dataset.homeDisplay || "";
      const homeAuthorityId = homeConfigEl.dataset.homeAuthorityId || "";

      const fromInput = document.querySelector(
        '[data-role="from-booking-input"]'
      );
      const fromAddBtn = document.querySelector(
        '[data-role="from-booking-add"]'
      );
      const fromList = document.getElementById("fromBookingLocationList");

      const destInput = document.querySelector(
        '[data-role="dest-booking-input"]'
      );
      const destAddBtn = document.querySelector(
        '[data-role="dest-booking-add"]'
      );
      const destList = document.getElementById("destBookingLocationList");

      const directionCol = document.getElementById("homeDirectionCol");

      function listHasCode(list, code) {
        if (!list || !code) return false;
        return !!list.querySelector('li[data-code="' + code + '"]');
      }

      function removeCodeFromList(list, code) {
        if (!list || !code) return;
        list.querySelectorAll('li[data-code="' + code + '"]').forEach((li) =>
          li.remove()
        );
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
          side = "LOADING"; // home is origin → loading side
        } else if (listType === "DEST") {
          if (!destInput || !destAddBtn || !destList) return;
          if (listHasCode(destList, homeCode)) return;
          input = destInput;
          addBtn = destAddBtn;
          list = destList;
          side = "UNLOADING"; // home is destination → unloading side
        } else {
          return;
        }

        // Add the home location li via existing logic
        input.value = homeDisplay;
        addBtn.click();

        // If no default authority configured, stop here
        if (!homeAuthorityId) return;

        // Find the li we just added
        const li = list.querySelector('li[data-code="' + homeCode + '"]');
        if (!li) return;

        const selectedContainer = li.querySelector(
          "[data-role='selected-authorities']"
        );
        const summaryDiv = li.querySelector("[data-role='authority-summary']");
        if (!selectedContainer || !summaryDiv) return;

        // Clear any existing selection for this li
        selectedContainer.innerHTML = "";

        // Create hidden input for this authority (loading_XXX[] or unloading_XXX[])
        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.value = homeAuthorityId;
        hidden.name =
          side === "LOADING"
            ? `loading_${homeCode}[]`
            : `unloading_${homeCode}[]`;

        selectedContainer.appendChild(hidden);

        // Update summary text using BOOKING_AUTH_BY_CODE
        const listForCode = BOOKING_AUTH_BY_CODE[homeCode] || [];
        const authNumericId = parseInt(homeAuthorityId, 10);
        const match = listForCode.find(
          (a) => Number(a.id) === authNumericId
        );

        if (match) {
          summaryDiv.textContent = match.title;
        } else {
          summaryDiv.textContent = "Default home authority";
        }
      }

      function syncHomeLocation() {
        const homeYes = document.getElementById("homeBookingYes");
        const homeNo = document.getElementById("homeBookingNo");
        const inboundRadio = document.getElementById("homeInbound");
        const outwardRadio = document.getElementById("homeOutward");

        const isHome =
          homeYes && homeYes.checked && (!homeNo || !homeNo.checked);

        // Show/hide the direction column based on home depot toggle
        if (directionCol) {
          if (isHome) {
            directionCol.classList.remove("d-none");
          } else {
            directionCol.classList.add("d-none");
          }
        }

        // If not a home depot booking, remove the home code from both lists
        if (!isHome) {
          removeCodeFromList(fromList, homeCode);
          removeCodeFromList(destList, homeCode);
          setKmSuggestions([]);
          return;
        }

        // Home depot ON → place home either in FROM or DEST based on direction
        const inboundSelected = inboundRadio && inboundRadio.checked;
        const outwardSelected = outwardRadio && outwardRadio.checked;

        // Remove from both first
        removeCodeFromList(fromList, homeCode);
        removeCodeFromList(destList, homeCode);

        if (inboundSelected) {
          // Inbound: far → home, so home at DEST
          addHomeTo("DEST");
        } else if (outwardSelected) {
          // Outward: home → far, so home at FROM
          addHomeTo("FROM");
        }

        // After any change to home placement, recompute KM suggestions
        recomputeHomeKmSuggestions();
      }

      ["homeBookingYes", "homeBookingNo", "homeInbound", "homeOutward"].forEach(
        (id) => {
          const el = document.getElementById(id);
          if (el) {
            el.addEventListener("change", syncHomeLocation);
          }
        }
      );

      // Initial state on page load
      syncHomeLocation();
    })();

    // ========================================
    // Authority Picker Modal Logic
    // ========================================
    const modalEl = document.getElementById("authorityPickerModal");
    const authorityModal = modalEl ? new bootstrap.Modal(modalEl) : null;

    let currentLi = null;

    document.addEventListener("click", function (e) {
      const btn = e.target.closest("button[data-role='open-authority-picker']");
      if (!btn) return;
      if (!authorityModal) return;

      const code = btn.dataset.code;
      const side = btn.dataset.side;
      currentLi = btn.closest("li");

      const authListDiv = document.getElementById("authorityPickerList");
      const emptyDiv = document.getElementById("authorityPickerEmpty");
      authListDiv.innerHTML = "";

      const list = BOOKING_AUTH_BY_CODE[code] || [];

      // Read already selected IDs from currentLi
      const selectedContainer = currentLi.querySelector(
        "[data-role='selected-authorities']"
      );
      const existingIds = Array.from(
        selectedContainer.querySelectorAll("input[type='hidden']")
      ).map((h) => h.value);

      if (!list.length) {
        emptyDiv.classList.remove("d-none");
      } else {
        emptyDiv.classList.add("d-none");
        list.forEach(function (a) {
          const checkWrapper = document.createElement("div");
          checkWrapper.className = "form-check";

          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.className = "form-check-input";
          cb.id = `auth-${side}-${code}-${a.id}`;
          cb.dataset.authId = a.id;

          if (existingIds.includes(String(a.id))) {
            cb.checked = true;
          }

          const label = document.createElement("label");
          label.className = "form-check-label ms-2";
          label.setAttribute("for", cb.id);
          label.textContent = a.title;

          checkWrapper.appendChild(cb);
          checkWrapper.appendChild(label);
          authListDiv.appendChild(checkWrapper);
        });
      }

      authorityModal.show();
    });

    const applyBtn = document.getElementById("applyAuthoritySelection");
    if (applyBtn) {
      applyBtn.addEventListener("click", function () {
        if (!currentLi) return;

        const side = currentLi.dataset.side;
        const code = currentLi.dataset.code;

        const container = currentLi.querySelector(
          "[data-role='selected-authorities']"
        );
        container.innerHTML = "";

        const selectedTitles = [];

        document
          .querySelectorAll("#authorityPickerList input[type='checkbox']")
          .forEach(function (cb) {
            if (cb.checked) {
              const hidden = document.createElement("input");
              hidden.type = "hidden";
              hidden.value = cb.dataset.authId;

              if (side === "LOADING") {
                hidden.name = `loading_${code}[]`;
              } else {
                hidden.name = `unloading_${code}[]`;
              }

              container.appendChild(hidden);

              const label = cb
                .closest(".form-check")
                .querySelector(".form-check-label");
              if (label) {
                selectedTitles.push(label.textContent.trim());
              }
            }
          });

        const summaryDiv = currentLi.querySelector(
          "[data-role='authority-summary']"
        );
        summaryDiv.textContent = selectedTitles.length
          ? selectedTitles.join(", ")
          : "None selected";

        authorityModal.hide();
      });
    }

    // ========================================
    // "Add new Authority" inside the modal
    // ========================================
    const newAuthTitleInput = document.getElementById("newAuthorityTitle");
    const newAuthAddressInput = document.getElementById("newAuthorityAddress");
    const newAuthStatus = document.getElementById("newAuthorityStatus");
    const btnAddAuthority = document.getElementById("btnAddAuthority");

    if (btnAddAuthority) {
      btnAddAuthority.addEventListener("click", function () {
        if (!currentLi) {
          newAuthStatus.textContent = "No location selected.";
          newAuthStatus.className = "small text-danger";
          return;
        }

        const code = currentLi.dataset.code;
        const title = (newAuthTitleInput.value || "").trim();
        const address = (newAuthAddressInput.value || "").trim();

        if (!title) {
          newAuthStatus.textContent = "Please enter a designation.";
          newAuthStatus.className = "small text-danger";
          return;
        }

        newAuthStatus.textContent = "Saving...";
        newAuthStatus.className = "small text-muted";
        btnAddAuthority.disabled = true;

        const csrfToken =
          window.CSRF_TOKEN ||
          (document.querySelector('meta[name="csrf-token"]')
            ? document
                .querySelector('meta[name="csrf-token"]')
                .getAttribute("content")
            : null);

        fetch(window.FLASK_QUICK_ADD_AUTHORITY_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(csrfToken
              ? {
                  "X-CSRFToken": csrfToken,
                  "X-CSRF-Token": csrfToken,
                }
              : {}),
          },
          body: JSON.stringify({
            location_code: code,
            title: title,
            address: address,
          }),
        })
          .then(async (resp) => {
            let data = null;
            try {
              data = await resp.json();
            } catch (e) {
              // non-JSON response (e.g., HTML error page)
            }

            if (!resp.ok || !data || data.success === false) {
              const msg =
                data && data.error
                  ? data.error
                  : `Server error (${resp.status}) while saving authority.`;
              throw new Error(msg);
            }

            return data;
          })
          .then((data) => {
            const auth = data.authority;

            newAuthStatus.textContent = "Authority added.";
            newAuthStatus.className = "small text-success";

            // Clear inputs
            newAuthTitleInput.value = "";
            newAuthAddressInput.value = "";

            // Update in-memory map so future openings see it
            if (!BOOKING_AUTH_BY_CODE[code]) {
              BOOKING_AUTH_BY_CODE[code] = [];
            }
            BOOKING_AUTH_BY_CODE[code].push({
              id: auth.id,
              title: auth.title,
            });

            // Add a new checkbox row to the current list and check it
            const listDiv = document.getElementById("authorityPickerList");
            const emptyDiv = document.getElementById("authorityPickerEmpty");
            if (emptyDiv) {
              emptyDiv.classList.add("d-none");
            }

            const checkWrapper = document.createElement("div");
            checkWrapper.className = "form-check";

            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.className = "form-check-input";
            cb.checked = true;
            cb.dataset.authId = auth.id;
            cb.id = `auth-${currentLi.dataset.side}-${code}-${auth.id}`;

            const label = document.createElement("label");
            label.className = "form-check-label ms-2";
            label.setAttribute("for", cb.id);
            label.textContent = auth.title;

            checkWrapper.appendChild(cb);
            checkWrapper.appendChild(label);
            listDiv.appendChild(checkWrapper);
          })
          .catch((err) => {
            newAuthStatus.textContent =
              (err && err.message) || "Error talking to server.";
            newAuthStatus.className = "small text-danger";
          })
          .finally(() => {
            btnAddAuthority.disabled = false;
          });
      });
    }

    // ========================================
    // Booking Details Modal (with materials)
    // ========================================
    (function setupBookingDetailsModal() {
      const detailModalEl = document.getElementById("bookingDetailModal");
      if (!detailModalEl) return;

      const materialsBody = document.getElementById(
        "bookingDetailMaterialsBody"
      );
      const materialsSummaryEl = document.getElementById(
        "bookingDetailMaterialsSummary"
      );

      function setText(id, value) {
        const el = document.getElementById(id);
        if (el) {
          el.textContent = value || "";
        }
      }

      function renderMaterialsPlaceholder(message) {
        if (!materialsBody) return;
        materialsBody.innerHTML =
          '<tr class="text-muted"><td colspan="6">' +
          message +
          "</td></tr>";
        if (materialsSummaryEl) {
          materialsSummaryEl.textContent = "";
        }
      }

      // Delegated click handler for any Details button in any tab
      document.addEventListener("click", function (event) {
        // Be lenient: any element with data-booking-id is treated as a trigger
        const button = event.target.closest("[data-booking-id]");
        if (!button) return;

        const ds = button.dataset;

        // Header fields
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

        // Always show modal immediately (with a loading placeholder in materials)
        if (materialsBody) {
          renderMaterialsPlaceholder("Loading materials…");
        }
        const modalInstance = bootstrap.Modal.getOrCreateInstance(detailModalEl);
        modalInstance.show();

        // Materials: load via JSON
        if (!materialsBody || !MATERIALS_URL_TEMPLATE) {
          return;
        }

        const bookingId = ds.bookingId;
        if (!bookingId) {
          renderMaterialsPlaceholder("No material details available.");
          return;
        }

        const url = MATERIALS_URL_TEMPLATE.replace("__ID__", bookingId);

        fetch(url, {
          headers: {
            Accept: "application/json",
          },
        })
          .then((resp) => {
            if (!resp.ok) {
              throw new Error("Server error " + resp.status);
            }
            return resp.json();
          })
          .then((data) => {
            if (!data || data.success === false || !data.has_materials) {
              renderMaterialsPlaceholder("No material details available.");
              return;
            }

            const lines = data.lines || [];
            const mode = (data.mode || "").toUpperCase();
            const header = data.header || {};

            if (!lines.length) {
              renderMaterialsPlaceholder("No material details available.");
            } else {
              materialsBody.innerHTML = "";

              lines.forEach((line, idx) => {
                const tr = document.createElement("tr");

                function td(text, align) {
                  const cell = document.createElement("td");
                  if (align) cell.classList.add("text-" + align);
                  cell.textContent =
                    text === null || text === undefined ? "" : String(text);
                  return cell;
                }

                const sl = line.sequence_index || idx + 1;
                tr.appendChild(td(sl, "center"));
                tr.appendChild(td(line.description || "", null));
                tr.appendChild(td(line.unit || "", "center"));
                tr.appendChild(
                  td(
                    line.quantity != null && line.quantity !== ""
                      ? line.quantity
                      : "",
                    "end"
                  )
                );
                tr.appendChild(
                  td(
                    line.rate != null && line.rate !== "" ? line.rate : "",
                    "end"
                  )
                );
                tr.appendChild(
                  td(
                    line.amount != null && line.amount !== ""
                      ? line.amount
                      : "",
                    "end"
                  )
                );

                materialsBody.appendChild(tr);
              });
            }

            // -------- Mode-aware summary ----------
            if (!materialsSummaryEl) return;

            const qtyHeader = header.total_quantity;
            const unitHeader = header.total_quantity_unit;
            const amtHeader = header.total_amount;

            // Detect if any line has quantity (for LUMPSUM logic)
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
              // For ITEM mode, header total qty/unit are not meaningful; focus on amount.
              if (amtHeader != null && amtHeader !== "") {
                materialsSummaryEl.textContent =
                  "Item-wise materials. Total amount: ₹ " + amtHeader;
              } else {
                materialsSummaryEl.textContent = "Item-wise materials.";
              }
            } else if (mode === "LUMPSUM") {
              let parts = ["Lumpsum materials"];

              if (!anyLineQty) {
                // No per-line qty: use header total qty/unit if present
                if (qtyHeader != null && qtyHeader !== "") {
                  parts.push(
                    "Total quantity: " +
                      qtyHeader +
                      (unitHeader ? " " + unitHeader : "")
                  );
                } else if (unitHeader) {
                  parts.push("Unit: " + unitHeader);
                }
              } // else: lines carry quantity; don't repeat header total qty

              if (amtHeader != null && amtHeader !== "") {
                parts.push("Total amount: ₹ " + amtHeader);
              }

              materialsSummaryEl.textContent = parts.join(" · ");
            } else {
              // No mode info
              materialsSummaryEl.textContent = "";
            }
          })
          .catch(() => {
            renderMaterialsPlaceholder(
              "Error loading material details from server."
            );
          });
      });
    })();

    // ========================================
    // Materials section (Booking materials editor)
    // ========================================
    (function setupMaterialsSection() {
      const modeSelect = document.getElementById("materialMode");
      const tbody = document.getElementById("materialLinesBody");
      const btnAddRow = document.getElementById("btnAddMaterialRow");
      const totalQtyGroup = document.getElementById("materialTotalQtyGroup");
      const totalQtyInput = document.querySelector(
        "input[name='material_total_quantity']"
      );
      const totalUnitInput = document.querySelector(
        "input[name='material_total_quantity_unit']"
      );
      const totalAmountInput = document.querySelector(
        "input[name='material_total_amount']"
      );

      if (!modeSelect || !tbody || !btnAddRow) {
        return; // not on this page
      }

      function renumberMaterialRows() {
        const rows = tbody.querySelectorAll("tr");
        rows.forEach(function (row, index) {
          const slCell = row.querySelector("[data-role='material-sl']");
          if (slCell) {
            slCell.textContent = index + 1;
          }
        });
      }

      function createMaterialRow() {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="text-center" data-role="material-sl"></td>
          <td>
            <input
              type="text"
              class="form-control form-control-sm"
              name="material_line_description[]"
              placeholder="Description"
            >
          </td>
          <td data-role="material-item-only">
            <input
              type="text"
              class="form-control form-control-sm material-unit"
              name="material_line_unit[]"
              placeholder="Unit"
              data-role="item-only-input"
            >
          </td>
          <td data-role="material-item-only">
            <input
              type="number"
              class="form-control form-control-sm material-qty"
              name="material_line_quantity[]"
              placeholder="Qty"
              step="0.01"
              min="0"
              data-role="item-only-input"
            >
          </td>
          <td data-role="material-item-only">
            <input
              type="number"
              class="form-control form-control-sm material-rate"
              name="material_line_rate[]"
              placeholder="Rate"
              step="0.01"
              min="0"
              data-role="item-only-input"
            >
          </td>
          <td data-role="material-item-only">
            <input
              type="number"
              class="form-control form-control-sm material-amount"
              name="material_line_amount[]"
              placeholder="Amount"
              step="0.01"
              min="0"
              data-role="item-only-input"
            >
          </td>
          <td class="text-center">
            <button type="button" class="btn btn-sm btn-outline-danger" data-role="material-remove-row">
              &times;
            </button>
          </td>
        `;
        return tr;
      }

      function addMaterialRow() {
        const row = createMaterialRow();
        tbody.appendChild(row);
        renumberMaterialRows();
        applyMaterialModeVisibility();
        updateLumpsumTotalQtyEnableState();
      }

      function recalcHeaderTotals() {
        const mode = modeSelect.value;
        if (mode !== "ITEM") {
          // In LUMPSUM or no mode, don't auto-override header totals
          return;
        }

        // ITEM mode: sum amounts (and quantities) and push to header
        let totalQty = 0;
        let totalAmt = 0;

        tbody.querySelectorAll("tr").forEach(function (row) {
          const qtyInput = row.querySelector(".material-qty");
          const amtInput = row.querySelector(".material-amount");

          if (qtyInput) {
            const q = parseFloat(qtyInput.value);
            if (!isNaN(q)) {
              totalQty += q;
            }
          }
          if (amtInput) {
            const a = parseFloat(amtInput.value);
            if (!isNaN(a)) {
              totalAmt += a;
            }
          }
        });

        if (totalQtyInput) {
          totalQtyInput.value = totalQty > 0 ? totalQty.toFixed(2) : "";
        }
        if (totalAmountInput) {
          totalAmountInput.value = totalAmt > 0 ? totalAmt.toFixed(2) : "";
        }
        // Unit is left to user; we don't infer unit.
      }

      function updateLumpsumTotalQtyEnableState() {
        const mode = modeSelect.value;
        if (mode !== "LUMPSUM") {
          // In ITEM or blank, we don't want user editing total qty/unit
          if (totalQtyInput) {
            totalQtyInput.disabled = true;
          }
          if (totalUnitInput) {
            totalUnitInput.disabled = true;
          }
          return;
        }

        let anyQtyFilled = false;
        tbody.querySelectorAll(".material-qty").forEach(function (input) {
          const v = parseFloat(input.value);
          if (!isNaN(v) && v > 0) {
            anyQtyFilled = true;
          }
        });

        if (totalQtyInput && totalUnitInput) {
          if (anyQtyFilled) {
            totalQtyInput.disabled = true;
            totalUnitInput.disabled = true;
          } else {
            totalQtyInput.disabled = false;
            totalUnitInput.disabled = false;
          }
        }
      }

      function applyMaterialModeVisibility() {
        const mode = modeSelect.value;

        const unitInputs = tbody.querySelectorAll(".material-unit");
        const qtyInputs = tbody.querySelectorAll(".material-qty");
        const rateInputs = tbody.querySelectorAll(".material-rate");
        const amountInputs = tbody.querySelectorAll(".material-amount");

        // td-level cells for rate/amount/unit/qty
        const rateCells = [];
        const amountCells = [];
        const unitCells = [];
        const qtyCells = [];

        rateInputs.forEach(function (inp) {
          if (inp.closest("td")) rateCells.push(inp.closest("td"));
        });
        amountInputs.forEach(function (inp) {
          if (inp.closest("td")) amountCells.push(inp.closest("td"));
        });
        unitInputs.forEach(function (inp) {
          if (inp.closest("td")) unitCells.push(inp.closest("td"));
        });
        qtyInputs.forEach(function (inp) {
          if (inp.closest("td")) qtyCells.push(inp.closest("td"));
        });

        if (mode === "ITEM") {
          // Show all item columns
          unitCells.forEach(function (td) {
            td.classList.remove("d-none");
          });
          qtyCells.forEach(function (td) {
            td.classList.remove("d-none");
          });
          rateCells.forEach(function (td) {
            td.classList.remove("d-none");
          });
          amountCells.forEach(function (td) {
            td.classList.remove("d-none");
          });

          // Enable all item inputs
          unitInputs.forEach((i) => i.removeAttribute("disabled"));
          qtyInputs.forEach((i) => i.removeAttribute("disabled"));
          rateInputs.forEach((i) => i.removeAttribute("disabled"));
          amountInputs.forEach((i) => i.removeAttribute("disabled"));

          // Hide total quantity group in ITEM mode
          if (totalQtyGroup) {
            totalQtyGroup.classList.add("d-none");
          }
          // Header totals in ITEM mode are computed only, not editable
          if (totalQtyInput) {
            totalQtyInput.disabled = true;
            totalQtyInput.value = "";
          }
          if (totalUnitInput) {
            totalUnitInput.disabled = true;
            // we don't forcibly clear unit; user may have set it meaningfully
          }
          if (totalAmountInput) {
            totalAmountInput.disabled = true;
          }
        } else if (mode === "LUMPSUM") {
          // LUMPSUM mode:
          // - Show Unit + Qty columns
          // - Hide Rate + Amount columns
          unitCells.forEach(function (td) {
            td.classList.remove("d-none");
          });
          qtyCells.forEach(function (td) {
            td.classList.remove("d-none");
          });
          rateCells.forEach(function (td) {
            td.classList.add("d-none");
          });
          amountCells.forEach(function (td) {
            td.classList.add("d-none");
          });

          // Enable Unit + Qty; disable Rate + Amount
          unitInputs.forEach((i) => i.removeAttribute("disabled"));
          qtyInputs.forEach((i) => i.removeAttribute("disabled"));
          rateInputs.forEach((i) => {
            i.value = "";
            i.setAttribute("disabled", "disabled");
          });
          amountInputs.forEach((i) => {
            i.value = "";
            i.setAttribute("disabled", "disabled");
          });

          // Show total quantity group (with conditional enable)
          if (totalQtyGroup) {
            totalQtyGroup.classList.remove("d-none");
          }
          if (totalAmountInput) {
            totalAmountInput.disabled = false;
          }
          updateLumpsumTotalQtyEnableState();
        } else {
          // No mode / blank:
          // Hide all item columns and disable all item inputs
          unitCells.forEach(function (td) {
            td.classList.add("d-none");
          });
          qtyCells.forEach(function (td) {
            td.classList.add("d-none");
          });
          rateCells.forEach(function (td) {
            td.classList.add("d-none");
          });
          amountCells.forEach(function (td) {
            td.classList.add("d-none");
          });

          unitInputs.forEach((i) => {
            i.setAttribute("disabled", "disabled");
          });
          qtyInputs.forEach((i) => {
            i.setAttribute("disabled", "disabled");
          });
          rateInputs.forEach((i) => {
            i.setAttribute("disabled", "disabled");
          });
          amountInputs.forEach((i) => {
            i.setAttribute("disabled", "disabled");
          });

          if (totalQtyGroup) {
            totalQtyGroup.classList.add("d-none");
          }
          if (totalQtyInput) {
            totalQtyInput.disabled = true;
            totalQtyInput.value = "";
          }
          if (totalUnitInput) {
            totalUnitInput.disabled = true;
            totalUnitInput.value = "";
          }
          if (totalAmountInput) {
            totalAmountInput.disabled = true;
            totalAmountInput.value = "";
          }
        }
      }

      function handleMaterialTableEvents(e) {
        const target = e.target;
        const mode = modeSelect.value;

        if (target.matches("[data-role='material-remove-row']")) {
          const row = target.closest("tr");
          if (row) {
            row.remove();
            if (tbody.children.length === 0) {
              addMaterialRow();
            } else {
              renumberMaterialRows();
            }
            recalcHeaderTotals();
            updateLumpsumTotalQtyEnableState();
          }
          return;
        }

        // ITEM mode: auto amount + totals
        if (
          mode === "ITEM" &&
          (target.classList.contains("material-qty") ||
            target.classList.contains("material-rate"))
        ) {
          const row = target.closest("tr");
          if (!row) return;

          const qtyInput = row.querySelector(".material-qty");
          const rateInput = row.querySelector(".material-rate");
          const amtInput = row.querySelector(".material-amount");

          if (!qtyInput || !rateInput || !amtInput) return;

          const qty = parseFloat(qtyInput.value);
          const rate = parseFloat(rateInput.value);

          if (!isNaN(qty) && !isNaN(rate)) {
            const amt = qty * rate;
            amtInput.value = amt > 0 ? amt.toFixed(2) : "";
          } else if (!qty && !rate) {
            amtInput.value = "";
          }
          recalcHeaderTotals();
          return;
        }

        if (mode === "ITEM" && target.classList.contains("material-amount")) {
          recalcHeaderTotals();
          return;
        }

        // LUMPSUM: respond to quantity changes by enabling/disabling total qty/unit
        if (mode === "LUMPSUM" && target.classList.contains("material-qty")) {
          updateLumpsumTotalQtyEnableState();
        }
      }

      // Wire up
      btnAddRow.addEventListener("click", function () {
        addMaterialRow();
      });

      tbody.addEventListener("click", handleMaterialTableEvents);
      tbody.addEventListener("input", handleMaterialTableEvents);

      modeSelect.addEventListener("change", function () {
        applyMaterialModeVisibility();
        recalcHeaderTotals();
      });

      // Initial state on page load
      if (tbody.children.length === 0) {
        addMaterialRow();
      } else {
        renumberMaterialRows();
        applyMaterialModeVisibility();
        updateLumpsumTotalQtyEnableState();
      }
    })();

    // ========================================
    // Booking detail page: materials editor
    // ========================================
    (function setupBookingDetailMaterials() {
      const modeSelect = document.getElementById("materialModeDetail");
      const tbody = document.getElementById("materialLinesBodyDetail");
      const btnAddRow = document.getElementById("btnAddMaterialRowDetail");
      const totalQtyGroup = document.getElementById(
        "materialTotalQtyGroupDetail"
      );

      // Only run on booking_detail.html
      if (!modeSelect || !tbody || !btnAddRow) {
        return;
      }

      const totalQtyInput = document.querySelector(
        "input[name='material_total_quantity']"
      );
      const totalUnitInput = document.querySelector(
        "input[name='material_total_quantity_unit']"
      );
      const totalAmountInput = document.querySelector(
        "input[name='material_total_amount']"
      );

      function parseFloatSafe(v) {
        if (v === null || v === undefined) return null;
        v = String(v).trim();
        if (!v) return null;
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      }

      function renumberRows() {
        const rows = tbody.querySelectorAll("tr");
        rows.forEach(function (row, index) {
          const slCell = row.querySelector(".seq-cell");
          if (slCell) {
            slCell.textContent = index + 1;
          }
        });
      }

      function createRow() {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="text-center seq-cell"></td>
          <td>
            <input type="hidden" name="line_id[]" value="">
            <input
              type="text"
              name="line_description[]"
              class="form-control form-control-sm"
              required
            >
          </td>
          <td>
            <input
              type="text"
              name="line_unit[]"
              class="form-control form-control-sm material-unit"
            >
          </td>
          <td>
            <input
              type="number"
              name="line_quantity[]"
              class="form-control form-control-sm material-qty"
              step="0.001"
              min="0"
            >
          </td>
          <td>
            <input
              type="number"
              name="line_rate[]"
              class="form-control form-control-sm material-rate"
              step="0.01"
              min="0"
            >
          </td>
          <td>
            <input
              type="number"
              name="line_amount[]"
              class="form-control form-control-sm material-amount"
              step="0.01"
              min="0"
            >
          </td>
          <td class="text-center">
            <button
              type="button"
              class="btn btn-sm btn-outline-danger"
              data-role="remove-material-line-detail"
            >
              ×
            </button>
          </td>
        `;
        return tr;
      }

      function addRow() {
        const row = createRow();
        tbody.appendChild(row);
        renumberRows();
        applyModeVisibility();
        updateLumpsumTotalQtyEnableState();
      }

      // ITEM mode → header totals derived from rows
      function recalcHeaderTotals() {
        const mode = modeSelect.value;
        if (mode !== "ITEM") return;

        let totalQty = 0;
        let totalAmt = 0;

        tbody.querySelectorAll("tr").forEach(function (row) {
          const qtyInput = row.querySelector(".material-qty");
          const amtInput = row.querySelector(".material-amount");

          const q = qtyInput ? parseFloatSafe(qtyInput.value) : null;
          const a = amtInput ? parseFloatSafe(amtInput.value) : null;

          if (q !== null) totalQty += q;
          if (a !== null) totalAmt += a;
        });

        if (totalQtyInput) {
          totalQtyInput.value = totalQty > 0 ? totalQty.toFixed(3) : "";
        }
        if (totalAmountInput) {
          totalAmountInput.value = totalAmt > 0 ? totalAmt.toFixed(2) : "";
        }
      }

      // LUMPSUM behaviour:
      // - If any row has Qty → disable header total qty/unit.
      // - Else if header total qty has value → disable all row qty and clear them.
      // - Else → both header and row quantities enabled.
      function updateLumpsumTotalQtyEnableState() {
        const mode = modeSelect.value;
        if (mode !== "LUMPSUM") return;
        if (!totalQtyInput || !totalUnitInput) return;

        let anyRowQty = false;
        tbody.querySelectorAll(".material-qty").forEach(function (input) {
          const v = parseFloatSafe(input.value);
          if (v !== null && v !== 0) {
            anyRowQty = true;
          }
        });

        const headerQty = parseFloatSafe(totalQtyInput.value);
        const headerHasQty = headerQty !== null && headerQty !== 0;

        if (anyRowQty) {
          // Row-level quantities take priority → lock header
          totalQtyInput.disabled = true;
          totalUnitInput.disabled = true;
        } else if (headerHasQty) {
          // Header total quantity in use → lock row quantities and clear them
          totalQtyInput.disabled = false;
          totalUnitInput.disabled = false;
          tbody.querySelectorAll(".material-qty").forEach(function (input) {
            input.value = "";
            input.disabled = true;
          });
        } else {
          // Nothing filled → allow both header and row quantities
          totalQtyInput.disabled = false;
          totalUnitInput.disabled = false;
          tbody.querySelectorAll(".material-qty").forEach(function (input) {
            input.disabled = false;
          });
        }
      }

      function applyModeVisibility() {
        const mode = modeSelect.value;

        const unitInputs = tbody.querySelectorAll(".material-unit");
        const qtyInputs = tbody.querySelectorAll(".material-qty");
        const rateInputs = tbody.querySelectorAll(".material-rate");
        const amountInputs = tbody.querySelectorAll(".material-amount");

        const unitCells = [];
        const qtyCells = [];
        const rateCells = [];
        const amountCells = [];

        unitInputs.forEach(function (inp) {
          const td = inp.closest("td");
          if (td) unitCells.push(td);
        });
        qtyInputs.forEach(function (inp) {
          const td = inp.closest("td");
          if (td) qtyCells.push(td);
        });
        rateInputs.forEach(function (inp) {
          const td = inp.closest("td");
          if (td) rateCells.push(td);
        });
        amountInputs.forEach(function (inp) {
          const td = inp.closest("td");
          if (td) amountCells.push(td);
        });

        if (mode === "ITEM") {
          // ITEM mode:
          // - All row columns visible and editable
          // - Header total qty/unit hidden & disabled
          unitCells.forEach((td) => td.classList.remove("d-none"));
          qtyCells.forEach((td) => td.classList.remove("d-none"));
          rateCells.forEach((td) => td.classList.remove("d-none"));
          amountCells.forEach((td) => td.classList.remove("d-none"));

          unitInputs.forEach((i) => i.removeAttribute("disabled"));
          qtyInputs.forEach((i) => i.removeAttribute("disabled"));
          rateInputs.forEach((i) => i.removeAttribute("disabled"));
          amountInputs.forEach((i) => i.removeAttribute("disabled"));

          if (totalQtyGroup) totalQtyGroup.classList.add("d-none");
          if (totalQtyInput) {
            totalQtyInput.disabled = true;
            totalQtyInput.value = "";
          }
          if (totalUnitInput) {
            totalUnitInput.disabled = true;
            totalUnitInput.value = "";
          }
          if (totalAmountInput) {
            totalAmountInput.disabled = true;
            totalAmountInput.value = "";
          }
        } else if (mode === "LUMPSUM") {
          // LUMPSUM mode:
          // - Show Unit + Qty
          // - Hide Rate + Amount (and disable them)
          // - Header total qty/unit visible
          unitCells.forEach((td) => td.classList.remove("d-none"));
          qtyCells.forEach((td) => td.classList.remove("d-none"));
          rateCells.forEach((td) => td.classList.add("d-none"));
          amountCells.forEach((td) => td.classList.add("d-none"));

          unitInputs.forEach((i) => {
            i.removeAttribute("disabled");
          });
          qtyInputs.forEach((i) => {
            i.removeAttribute("disabled");
          });
          rateInputs.forEach((i) => {
            i.value = "";
            i.setAttribute("disabled", "disabled");
          });
          amountInputs.forEach((i) => {
            i.value = "";
            i.setAttribute("disabled", "disabled");
          });

          if (totalQtyGroup) totalQtyGroup.classList.remove("d-none");
          if (totalAmountInput) {
            totalAmountInput.disabled = false;
          }
          updateLumpsumTotalQtyEnableState();
        } else {
          // No mode:
          // - Hide Unit/Qty/Rate/Amount
          // - Disable & clear all numeric/unit fields
          unitCells.forEach((td) => td.classList.add("d-none"));
          qtyCells.forEach((td) => td.classList.add("d-none"));
          rateCells.forEach((td) => td.classList.add("d-none"));
          amountCells.forEach((td) => td.classList.add("d-none"));

          [unitInputs, qtyInputs, rateInputs, amountInputs].forEach(function (
            nodeList
          ) {
            nodeList.forEach(function (i) {
              i.value = "";
              i.setAttribute("disabled", "disabled");
            });
          });

          if (totalQtyGroup) totalQtyGroup.classList.add("d-none");
          if (totalQtyInput) {
            totalQtyInput.disabled = true;
            totalQtyInput.value = "";
          }
          if (totalUnitInput) {
            totalUnitInput.disabled = true;
            totalUnitInput.value = "";
          }
          if (totalAmountInput) {
            totalAmountInput.disabled = true;
            totalAmountInput.value = "";
          }
        }
      }

      function handleTableEvents(e) {
        const target = e.target;
        const mode = modeSelect.value;

        // Remove row
        if (target.matches("[data-role='remove-material-line-detail']")) {
          const row = target.closest("tr");
          if (row) {
            row.remove();
            if (tbody.children.length === 0) {
              addRow();
            } else {
              renumberRows();
            }
            recalcHeaderTotals();
            updateLumpsumTotalQtyEnableState();
          }
          return;
        }

        // ITEM mode: auto amount + header totals
        if (
          mode === "ITEM" &&
          (target.classList.contains("material-qty") ||
            target.classList.contains("material-rate"))
        ) {
          const row = target.closest("tr");
          if (!row) return;

          const qtyInput = row.querySelector(".material-qty");
          const rateInput = row.querySelector(".material-rate");
          const amtInput = row.querySelector(".material-amount");

          if (!qtyInput || !rateInput || !amtInput) return;

          const q = parseFloatSafe(qtyInput.value);
          const r = parseFloatSafe(rateInput.value);

          if (q !== null && r !== null) {
            amtInput.value = (q * r).toFixed(2);
          } else {
            amtInput.value = "";
          }

          recalcHeaderTotals();
        }

        // LUMPSUM: keep header vs per-line qty rules in sync
        if (mode === "LUMPSUM" && target.classList.contains("material-qty")) {
          updateLumpsumTotalQtyEnableState();
        }
      }

      // Wire events
      btnAddRow.addEventListener("click", function () {
        addRow();
      });

      tbody.addEventListener("click", handleTableEvents);
      tbody.addEventListener("input", handleTableEvents);

      if (modeSelect) {
        modeSelect.addEventListener("change", function () {
          applyModeVisibility();
          recalcHeaderTotals();
          updateLumpsumTotalQtyEnableState();
        });
      }

      if (totalQtyInput) {
        totalQtyInput.addEventListener("input", function () {
          updateLumpsumTotalQtyEnableState();
        });
      }

      // Initial setup
      if (!tbody.querySelector("tr")) {
        addRow();
      } else {
        renumberRows();
        applyModeVisibility();
        updateLumpsumTotalQtyEnableState();
        recalcHeaderTotals();
      }
    })();

    // ========================================
    // Booking detail: placement date confirmation
    // ========================================
    (function setupPlacementDateConfirm() {
      const placementInput = document.getElementById("editPlacementDate");
      if (!placementInput) return;

      const form = placementInput.closest("form");
      if (!form) return;

      // We assume the disabled text input in this form holds booking_date as ISO (YYYY-MM-DD)
      const bookingDateInput = form.querySelector(
        "input[disabled][type='text']"
      );
      const bookingDateStr = bookingDateInput
        ? bookingDateInput.value.trim()
        : "";

      // Today's date (editing date) as ISO YYYY-MM-DD
      const today = new Date();
      const yyyy = today.getFullYear();
      const mm = String(today.getMonth() + 1).padStart(2, "0");
      const dd = String(today.getDate()).padStart(2, "0");
      const todayStr = `${yyyy}-${mm}-${dd}`;

      form.addEventListener("submit", function (evt) {
        if (!placementInput.value || !bookingDateStr) {
          return;
        }

        const newDate = placementInput.value.trim(); // from <input type="date">, ISO format

        // We only warn when user is back-dating:
        // booking_date < newDate < today
        if (newDate > bookingDateStr && newDate < todayStr) {
          const ok = window.confirm(
            "Placement date (" +
              newDate +
              ") is earlier than today (" +
              todayStr +
              ") but after the booking date (" +
              bookingDateStr +
              ").\n\n" +
              "Do you want to proceed with this back-dated placement?"
          );
          if (!ok) {
            evt.preventDefault();
          }
        }
      });
    })();

  });
}
