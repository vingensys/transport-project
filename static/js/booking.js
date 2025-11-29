// static/js/booking.js

document.addEventListener("DOMContentLoaded", function () {
  // This is injected from the template via:
  // window.BOOKING_AUTH_BY_CODE = {{ booking_auth_map|tojson }};
  const BOOKING_AUTH_BY_CODE = window.BOOKING_AUTH_BY_CODE || {};

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
});
