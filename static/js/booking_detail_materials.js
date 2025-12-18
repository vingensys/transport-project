// transport/static/js/booking_detail_materials.js
(function () {
  const form = document.getElementById("materialEditFormDetail");
  const scopesJSON = document.getElementById("materialsScopesJSONDetail");
  const accordion = document.getElementById("materialsScopesAccordionDetail");

  // If this page is not in multiscope mode, these elements won't exist.
  if (!form || !scopesJSON || !accordion) return;

  // ----------------------------
  // Utilities
  // ----------------------------
  function s(v) {
    return (v ?? "").toString().trim();
  }
  function modeOf(v) {
    return s(v).toUpperCase();
  }
  function num(v) {
    const t = s(v);
    if (!t) return null;
    const n = Number(t);
    return Number.isFinite(n) ? n : null;
  }
  function dis(el, yes) {
    if (el) el.disabled = !!yes;
  }
  function fmt2(n) {
    if (!Number.isFinite(n)) return "";
    return n.toFixed(2);
  }

  function scopeFromChild(el) {
    return el ? el.closest(".accordion-item") : null;
  }

  function clearEl(el) {
    if (el) el.value = "";
  }

  function clearLineField(scopeEl, selector) {
    scopeEl.querySelectorAll(selector).forEach((el) => (el.value = ""));
  }

  function clearAllLineNumbers(scopeEl) {
    clearLineField(scopeEl, ".scope-qty");
    clearLineField(scopeEl, ".scope-rate");
    clearLineField(scopeEl, ".scope-amount");
  }

  function clearAllLineFields(scopeEl) {
    clearLineField(scopeEl, ".scope-desc");
    clearLineField(scopeEl, ".scope-unit");
    clearAllLineNumbers(scopeEl);
  }

  function clearHeader(scopeEl, which) {
    const totalQtyEl = scopeEl.querySelector(".scope-total-qty");
    const totalUnitEl = scopeEl.querySelector(".scope-total-unit");
    const totalAmtEl = scopeEl.querySelector(".scope-total-amount");

    if (which === "QTY") {
      clearEl(totalQtyEl);
      clearEl(totalUnitEl);
    } else if (which === "AMOUNT") {
      clearEl(totalAmtEl);
    } else if (which === "ALL") {
      clearEl(totalQtyEl);
      clearEl(totalUnitEl);
      clearEl(totalAmtEl);
    }
  }

  function renumberRows(scopeEl) {
    const rows = scopeEl.querySelectorAll(
      'tbody[data-role="scope-lines"] tr[data-role="scope-line"]'
    );
    rows.forEach((tr, idx) => {
      const td = tr.querySelector("td");
      if (td) td.textContent = String(idx + 1);
    });
  }

  function addRow(scopeEl) {
    const tbody = scopeEl.querySelector('tbody[data-role="scope-lines"]');
    if (!tbody) return;

    const nextIndex =
      tbody.querySelectorAll('tr[data-role="scope-line"]').length + 1;

    const tr = document.createElement("tr");
    tr.setAttribute("data-role", "scope-line");
    tr.innerHTML = `
      <td class="text-center align-middle">${nextIndex}</td>
      <td><input type="text" class="form-control form-control-sm scope-desc" value="" required></td>
      <td><input type="text" class="form-control form-control-sm scope-unit" value=""></td>
      <td><input type="number" class="form-control form-control-sm scope-qty" step="0.001" min="0"></td>
      <td><input type="number" class="form-control form-control-sm scope-rate" step="0.01" min="0"></td>
      <td><input type="number" class="form-control form-control-sm scope-amount" step="0.01" min="0"></td>
      <td class="text-center">
        <button type="button" class="btn btn-sm btn-outline-danger" data-role="remove-scope-line">×</button>
      </td>
    `;
    tbody.appendChild(tr);
    renumberRows(scopeEl);
    applyScopeRules(scopeEl);
  }

  function getEls(scopeEl) {
    const modeSel = scopeEl.querySelector('[data-role="scope-mode"]');
    const badge = scopeEl.querySelector('[data-role="scope-mode-badge"]');

    const totalQtyEl = scopeEl.querySelector(".scope-total-qty");
    const totalUnitEl = scopeEl.querySelector(".scope-total-unit");
    const totalAmtEl = scopeEl.querySelector(".scope-total-amount");

    const addRowBtn = scopeEl.querySelector('[data-role="add-scope-row"]');

    const rows = scopeEl.querySelectorAll(
      'tbody[data-role="scope-lines"] tr[data-role="scope-line"]'
    );

    return {
      modeSel,
      badge,
      totalQtyEl,
      totalUnitEl,
      totalAmtEl,
      addRowBtn,
      rows,
    };
  }

  function syncModeBadge(scopeEl) {
    const { modeSel, badge } = getEls(scopeEl);
    if (badge) badge.textContent = modeSel && modeSel.value ? modeSel.value : "-";
  }

  // ----------------------------
  // Rule helpers
  // ----------------------------
  function anyLineQty(scopeEl) {
    const rows = scopeEl.querySelectorAll(
      'tbody[data-role="scope-lines"] tr[data-role="scope-line"]'
    );
    for (const tr of rows) {
      const qEl = tr.querySelector(".scope-qty");
      if (qEl && num(qEl.value) !== null) return true;
    }
    return false;
  }

  function headerQtyPresent(scopeEl) {
    const q = scopeEl.querySelector(".scope-total-qty");
    return q && num(q.value) !== null;
  }

  function computeItem(scopeEl) {
    // ITEM: line amount = qty*rate, header amount = sum
    const rows = scopeEl.querySelectorAll(
      'tbody[data-role="scope-lines"] tr[data-role="scope-line"]'
    );

    let total = 0;

    rows.forEach((tr) => {
      const qtyEl = tr.querySelector(".scope-qty");
      const rateEl = tr.querySelector(".scope-rate");
      const amtEl = tr.querySelector(".scope-amount");

      const q = qtyEl ? num(qtyEl.value) : null;
      const r = rateEl ? num(rateEl.value) : null;

      if (q !== null && r !== null) {
        const a = q * r;
        if (amtEl) amtEl.value = fmt2(a);
        total += a;
      } else {
        if (amtEl) amtEl.value = "";
      }
    });

    const totalAmtEl = scopeEl.querySelector(".scope-total-amount");
    if (totalAmtEl) totalAmtEl.value = fmt2(total);
  }

  function normalizeAttached(scopeEl) {
    const tbody = scopeEl.querySelector('tbody[data-role="scope-lines"]');
    if (!tbody) return;

    let firstRow = tbody.querySelector('tr[data-role="scope-line"]');
    if (!firstRow) {
      addRow(scopeEl);
      firstRow = tbody.querySelector('tr[data-role="scope-line"]');
      if (!firstRow) return;
    }

    // enforce placeholder
    const descEl = firstRow.querySelector(".scope-desc");
    if (descEl) descEl.value = "As per list attached.";

    // clear any line numeric/unit fields
    const unitEl = firstRow.querySelector(".scope-unit");
    const qtyEl = firstRow.querySelector(".scope-qty");
    const rateEl = firstRow.querySelector(".scope-rate");
    const amtEl = firstRow.querySelector(".scope-amount");
    if (unitEl) unitEl.value = "";
    if (qtyEl) qtyEl.value = "";
    if (rateEl) rateEl.value = "";
    if (amtEl) amtEl.value = "";

    // keep only one row
    const allRows = tbody.querySelectorAll('tr[data-role="scope-line"]');
    allRows.forEach((tr, idx) => {
      if (idx > 0) tr.remove();
    });
    renumberRows(scopeEl);
  }

  function cleanupOnModeSwitch(scopeEl, prevMode, nextMode) {
    prevMode = (prevMode || "").toUpperCase();
    nextMode = (nextMode || "").toUpperCase();

    // ITEM → LUMPSUM: clear illegal line fields (rate, amount)
    if (prevMode === "ITEM" && nextMode === "LUMPSUM") {
      clearLineField(scopeEl, ".scope-rate");
      clearLineField(scopeEl, ".scope-amount");
      return;
    }

    // ITEM → ATTACHED: everything except header total amount illegal
    if (prevMode === "ITEM" && nextMode === "ATTACHED") {
      clearAllLineFields(scopeEl);
      clearHeader(scopeEl, "QTY");
      return;
    }

    // LUMPSUM → ATTACHED: same cleanup
    if (prevMode === "LUMPSUM" && nextMode === "ATTACHED") {
      clearAllLineFields(scopeEl);
      clearHeader(scopeEl, "QTY");
      return;
    }

    // ATTACHED → ITEM: clear qty/unit; amounts recomputed
    if (prevMode === "ATTACHED" && nextMode === "ITEM") {
      clearHeader(scopeEl, "QTY");
      clearLineField(scopeEl, ".scope-amount");
      return;
    }

    // LUMPSUM → ITEM: clear header qty/unit; amounts recomputed
    if (prevMode === "LUMPSUM" && nextMode === "ITEM") {
      clearHeader(scopeEl, "QTY");
      clearLineField(scopeEl, ".scope-amount");
      return;
    }

    // ATTACHED → LUMPSUM: clear qty/unit (still ok), clear line numeric just in case
    if (prevMode === "ATTACHED" && nextMode === "LUMPSUM") {
      clearLineField(scopeEl, ".scope-rate");
      clearLineField(scopeEl, ".scope-amount");
      return;
    }
  }

  // ----------------------------
  // Apply per-scope UI rules
  // ----------------------------
  function applyScopeRules(scopeEl) {
    if (!scopeEl) return;

    const { modeSel, totalQtyEl, totalUnitEl, totalAmtEl, addRowBtn } = getEls(scopeEl);
    const mode = modeOf(modeSel?.value);

    const rows = scopeEl.querySelectorAll(
      'tbody[data-role="scope-lines"] tr[data-role="scope-line"]'
    );

    // collect inputs per row
    const descEls = [];
    const unitEls = [];
    const qtyEls = [];
    const rateEls = [];
    const amtEls = [];

    rows.forEach((tr) => {
      descEls.push(tr.querySelector(".scope-desc"));
      unitEls.push(tr.querySelector(".scope-unit"));
      qtyEls.push(tr.querySelector(".scope-qty"));
      rateEls.push(tr.querySelector(".scope-rate"));
      amtEls.push(tr.querySelector(".scope-amount"));
    });

    // reset enabled, then lock as needed
    dis(totalQtyEl, false);
    dis(totalUnitEl, false);
    dis(totalAmtEl, false);
    dis(addRowBtn, false);

    descEls.forEach((el) => dis(el, false));
    unitEls.forEach((el) => dis(el, false));
    qtyEls.forEach((el) => dis(el, false));
    rateEls.forEach((el) => dis(el, false));
    amtEls.forEach((el) => dis(el, false));

    // ---- ITEM ----
    if (mode === "ITEM") {
      // header qty/unit not used
      dis(totalQtyEl, true);
      dis(totalUnitEl, true);

      // header total amount derived
      dis(totalAmtEl, true);

      // line amount derived
      amtEls.forEach((el) => dis(el, true));

      // compute totals now
      computeItem(scopeEl);
      return;
    }

    // ---- LUMPSUM ----
    if (mode === "LUMPSUM") {
      // Per your rule: in LS only description + qty are active.
      // Unit editable (kept enabled), but rate/amount must be disabled.
      rateEls.forEach((el) => dis(el, true));
      amtEls.forEach((el) => dis(el, true));

      // If switching into LS left stale values, we also keep them cleared:
      rateEls.forEach((el) => (el ? (el.value = "") : null));
      amtEls.forEach((el) => (el ? (el.value = "") : null));

      // Mutual exclusion:
      // - if any line qty exists => lock header qty/unit
      // - else if header qty exists => lock line qty
      const hasLineQty = anyLineQty(scopeEl);
      const hasHeaderQty = headerQtyPresent(scopeEl);

      if (hasLineQty) {
        dis(totalQtyEl, true);
        dis(totalUnitEl, true);
      } else if (hasHeaderQty) {
        qtyEls.forEach((el) => dis(el, true));
      }

      // Header total amount: editable (allowed)
      return;
    }

    // ---- ATTACHED ----
    if (mode === "ATTACHED") {
      // only header total amount should be editable
      dis(totalQtyEl, true);
      dis(totalUnitEl, true);

      // disable all rows + add row
      dis(addRowBtn, true);
      descEls.forEach((el) => dis(el, true));
      unitEls.forEach((el) => dis(el, true));
      qtyEls.forEach((el) => dis(el, true));
      rateEls.forEach((el) => dis(el, true));
      amtEls.forEach((el) => dis(el, true));

      normalizeAttached(scopeEl);
      return;
    }

    // mode empty/unknown => leave as-is
  }

  // ----------------------------
  // Payload serialization
  // ----------------------------
  function getScopePayload(scopeEl) {
    const fromAuthId = scopeEl.getAttribute("data-from-authority-id");
    const toAuthId = scopeEl.getAttribute("data-to-authority-id");

    const modeSel = scopeEl.querySelector('[data-role="scope-mode"]');
    const mode = (modeSel ? modeSel.value : "").trim();

    const totalQtyEl = scopeEl.querySelector(".scope-total-qty");
    const totalUnitEl = scopeEl.querySelector(".scope-total-unit");
    const totalAmtEl = scopeEl.querySelector(".scope-total-amount");

    const total_quantity = totalQtyEl && s(totalQtyEl.value) ? s(totalQtyEl.value) : null;
    const total_quantity_unit = totalUnitEl && s(totalUnitEl.value) ? s(totalUnitEl.value) : null;
    const total_amount = totalAmtEl && s(totalAmtEl.value) ? s(totalAmtEl.value) : null;

    const lines = [];
    const rows = scopeEl.querySelectorAll(
      'tbody[data-role="scope-lines"] tr[data-role="scope-line"]'
    );

    rows.forEach((tr) => {
      const desc = (tr.querySelector(".scope-desc")?.value || "").trim();
      const unit = (tr.querySelector(".scope-unit")?.value || "").trim();
      const qty = (tr.querySelector(".scope-qty")?.value || "").trim();
      const rate = (tr.querySelector(".scope-rate")?.value || "").trim();
      const amt = (tr.querySelector(".scope-amount")?.value || "").trim();

      // Skip fully empty rows
      if (!desc && !unit && !qty && !rate && !amt) return;

      lines.push({
        description: desc,
        unit: unit || null,
        quantity: qty || null,
        rate: rate || null,
        amount: amt || null,
      });
    });

    return {
      from: { authority_id: fromAuthId ? Number(fromAuthId) : null },
      to: { authority_id: toAuthId ? Number(toAuthId) : null },
      material: {
        mode: mode,
        total_quantity: total_quantity,
        total_quantity_unit: total_quantity_unit,
        total_amount: total_amount,
        lines: lines,
      },
    };
  }

  // ----------------------------
  // Events (delegation)
  // ----------------------------
  accordion.addEventListener("click", function (e) {
    const addBtn = e.target.closest('[data-role="add-scope-row"]');
    if (addBtn) {
      const scopeEl = scopeFromChild(addBtn);
      if (scopeEl) addRow(scopeEl);
      return;
    }

    const rmBtn = e.target.closest('[data-role="remove-scope-line"]');
    if (rmBtn) {
      const scopeEl = scopeFromChild(rmBtn);
      const tr = rmBtn.closest('tr[data-role="scope-line"]');
      if (tr) tr.remove();
      if (scopeEl) {
        renumberRows(scopeEl);
        applyScopeRules(scopeEl);
      }
      return;
    }
  });

  accordion.addEventListener("change", function (e) {
    const modeSel = e.target.closest('[data-role="scope-mode"]');
    if (!modeSel) return;

    const scopeEl = scopeFromChild(modeSel);
    if (!scopeEl) return;

    const prevMode = scopeEl.getAttribute("data-prev-mode") || "";
    const nextMode = (modeSel.value || "").trim().toUpperCase();

    // cleanup conflicting data first
    cleanupOnModeSwitch(scopeEl, prevMode, nextMode);

    // store new prev mode
    scopeEl.setAttribute("data-prev-mode", nextMode);

    // badge sync
    syncModeBadge(scopeEl);

    // apply enable/disable rules
    applyScopeRules(scopeEl);
  });

  accordion.addEventListener("input", function (e) {
    const scopeEl = scopeFromChild(e.target);
    if (!scopeEl) return;

    const mode = modeOf(getEls(scopeEl).modeSel?.value);

    if (mode === "ITEM") {
      if (e.target.classList.contains("scope-qty") || e.target.classList.contains("scope-rate")) {
        computeItem(scopeEl);
      }
      return;
    }

    if (mode === "LUMPSUM") {
      // line qty OR header qty affects mutual exclusion locks
      if (
        e.target.classList.contains("scope-qty") ||
        e.target.classList.contains("scope-total-qty")
      ) {
        applyScopeRules(scopeEl);
      }
      return;
    }
  });

  form.addEventListener("submit", function () {
    const scopeEls = accordion.querySelectorAll(".accordion-item[data-scope-index]");
    const scopes = [];

    scopeEls.forEach((scopeEl) => {
      // ensure ITEM totals computed before submit
      applyScopeRules(scopeEl);
      scopes.push(getScopePayload(scopeEl));
    });

    scopesJSON.value = JSON.stringify({
      mode: "AUTHORITY_PAIR",
      scopes: scopes,
    });
  });

  // ----------------------------
  // Init (single pass)
  // ----------------------------
  (function init() {
    const scopeEls = accordion.querySelectorAll(".accordion-item[data-scope-index]");
    scopeEls.forEach((scopeEl) => {
      const modeSel = scopeEl.querySelector('[data-role="scope-mode"]');
      const mode = (modeSel ? modeSel.value : "").trim().toUpperCase();
      scopeEl.setAttribute("data-prev-mode", mode);

      syncModeBadge(scopeEl);
      renumberRows(scopeEl);
      applyScopeRules(scopeEl);
    });
  })();
})();
