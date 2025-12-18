from flask import request, redirect, url_for, flash, jsonify, render_template
from datetime import date, datetime
from typing import Optional, Tuple
import json

from transport.models import (
    db,
    Authority,
    Booking,
    Route,
    Location,
    RouteStop,
    Agreement,
    LorryDetails,
    BookingAuthority,
    BookingMaterial,
    BookingMaterialLine,
)

from transport.route_utils import build_route_code_and_name
from . import admin_bp


def _redirect_to_tab(tab_hash: str):
    """Redirect back to a specific dashboard tab (e.g., '#booking')."""
    return redirect(url_for("admin.dashboard") + tab_hash)


def _normalize_codes(codes):
    """Strip and uppercase location codes, dropping blanks."""
    return [c.strip().upper() for c in codes if c and c.strip()]


def _parse_materials_from_request():
    """
    Parse and validate materials from request.form (booking creation forms).

    Modes:
      - ITEM:
          * At least one line required
          * Each line: qty+rate together (or both blank)
          * Amount auto-computed when qty+rate present
          * User must not type amount alone
          * At least one computed amount must exist (not just descriptions)
          * Header total_amount is derived as sum(line.amount)
      - LUMPSUM:
          * Must have header (qty/amount/unit) OR at least one line
          * If header total_qty is given, line quantities must not be used
          * Lines can have partial numbers (desc mandatory if row exists)
      - ATTACHED:
          * Must have ONLY header total_amount (required)
          * No header qty/unit
          * No qty/rate/amount in lines
          * Stores a single placeholder line: "As per list attached."
    """
    material_payload = None
    material_number_error = False

    material_mode_raw = (request.form.get("material_mode") or "").strip().upper()

    header_qty_str = (request.form.get("material_total_quantity") or "").strip()
    header_qty_unit = (request.form.get("material_total_quantity_unit") or "").strip()
    header_amount_str = (request.form.get("material_total_amount") or "").strip()

    header_qty = None
    header_amount = None

    # -------------------------------
    # ATTACHED: ignore UI noise early
    # -------------------------------
    if material_mode_raw == "ATTACHED":
        header_amount_str = (request.form.get("material_total_amount") or "").strip()
        if not header_amount_str:
            flash("In ATTACHED mode, Total Amount is required.", "error")
            return None
        try:
            header_amount = float(header_amount_str)
        except ValueError:
            flash("Invalid number in Total Amount for ATTACHED mode.", "error")
            return None

        return {
            "mode": "ATTACHED",
            "total_quantity": None,
            "total_quantity_unit": None,
            "total_amount": header_amount,
            "lines": [
                {
                    "description": "As per list attached.",
                    "unit": None,
                    "quantity": None,
                    "rate": None,
                    "amount": None,
                }
            ],
        }

    # Parse header numbers (lenient: if blank → None)
    if header_qty_str:
        try:
            header_qty = float(header_qty_str)
        except ValueError:
            material_number_error = True

    if header_amount_str:
        try:
            header_amount = float(header_amount_str)
        except ValueError:
            material_number_error = True

    # Per-line fields
    line_descs = request.form.getlist("material_line_description[]")
    line_units = request.form.getlist("material_line_unit[]")
    line_qty_strs = request.form.getlist("material_line_quantity[]")
    line_rate_strs = request.form.getlist("material_line_rate[]")
    line_amount_strs = request.form.getlist("material_line_amount[]")

    lines_data = []
    max_len = (
        max(
            len(line_descs),
            len(line_units),
            len(line_qty_strs),
            len(line_rate_strs),
            len(line_amount_strs),
        )
        if (line_descs or line_units or line_qty_strs or line_rate_strs or line_amount_strs)
        else 0
    )

    # --- Parse rows ---
    for idx in range(max_len):
        desc = (line_descs[idx] if idx < len(line_descs) else "").strip()
        unit = (line_units[idx] if idx < len(line_units) else "").strip()
        qty_str = (line_qty_strs[idx] if idx < len(line_qty_strs) else "").strip()
        rate_str = (line_rate_strs[idx] if idx < len(line_rate_strs) else "").strip()
        amount_str = (line_amount_strs[idx] if idx < len(line_amount_strs) else "").strip()

        # Entirely empty row → skip
        if not (desc or unit or qty_str or rate_str or amount_str):
            continue

        # Description is mandatory for any non-empty row
        if not desc:
            flash(
                "Each material row must have a description if any other field is filled.",
                "error",
            )
            return None

        qty = None
        rate = None
        amount = None

        if qty_str:
            try:
                qty = float(qty_str)
            except ValueError:
                material_number_error = True

        if rate_str:
            try:
                rate = float(rate_str)
            except ValueError:
                material_number_error = True

        if amount_str:
            try:
                amount = float(amount_str)
            except ValueError:
                material_number_error = True

        # If any number parsing failed, stop after loop with a single message
        if material_number_error:
            continue

        # --- Mode-specific compute/validation at line level ---
        if material_mode_raw == "ITEM":
            # In ITEM mode: qty+rate must come together (or both blank)
            if (qty is None) ^ (rate is None):
                flash(
                    "In ITEM mode, each material row must have BOTH Quantity and Rate (or leave both blank).",
                    "error",
                )
                return None

            # Amount must not be manually entered without qty+rate
            if qty is None and rate is None and amount is not None:
                flash(
                    "In ITEM mode, do not enter Amount unless Quantity and Rate are provided (Amount is auto-calculated).",
                    "error",
                )
                return None

            # Compute amount when qty+rate present
            if qty is not None and rate is not None:
                amount = qty * rate

        elif material_mode_raw == "ATTACHED":
            # ATTACHED: lines must not carry qty/rate/amount; description will be normalized later
            if qty is not None or rate is not None or amount is not None:
                flash(
                    "In ATTACHED mode, do not enter Quantity/Rate/Amount in lines. Use only the header Total Amount.",
                    "error",
                )
                return None

        # LUMPSUM: allow partial fields (desc mandatory), header-vs-line qty invariant checked later.

        lines_data.append(
            {
                "description": desc,
                "unit": unit or None,
                "quantity": qty,
                "rate": rate,
                "amount": amount,
            }
        )

    if material_number_error:
        flash(
            "Invalid number in materials section. Please check quantity, rate and amount fields.",
            "error",
        )
        return None

    has_header_values = bool(
        header_qty is not None or header_amount is not None or header_qty_unit
    )
    has_lines = bool(lines_data)

    # From now on, *every* booking must include some materials.
    # 1) Mode must be chosen
    if not material_mode_raw:
        flash(
            "Each booking must include a material list. "
            "Choose ITEM, LUMPSUM, or ATTACHED and enter the required fields.",
            "error",
        )
        return None

    # 2) Mode must be valid
    if material_mode_raw not in ("ITEM", "LUMPSUM", "ATTACHED"):
        flash("Material mode must be ITEM, LUMPSUM, or ATTACHED.", "error")
        return None

    # 3) Per-mode minimum content
    if material_mode_raw == "ITEM":
        if not has_lines:
            flash("In ITEM mode, enter at least one material line.", "error")
            return None

        # IMPORTANT: In ITEM mode, ensure at least one computed amount exists
        if not any(line.get("amount") is not None for line in lines_data):
            flash(
                "In ITEM mode, at least one row must include Quantity and Rate so Amount can be computed.",
                "error",
            )
            return None

    elif material_mode_raw == "LUMPSUM":
        if not has_header_values and not has_lines:
            flash(
                "In LUMPSUM mode, enter a header quantity/amount or at least one material line.",
                "error",
            )
            return None

        # LUMPSUM-specific validation: header total quantity vs per-line quantities
        has_header_qty = header_qty is not None
        has_line_qty = any(line["quantity"] is not None for line in lines_data)
        if has_header_qty and has_line_qty:
            flash(
                "In LUMPSUM mode, use either the header total quantity or per-line quantities, not both.",
                "error",
            )
            return None

    elif material_mode_raw == "ATTACHED":
        # Must have header total amount
        if header_amount is None:
            flash("In ATTACHED mode, Total Amount is required.", "error")
            return None

        # No header qty/unit allowed
        if header_qty is not None or header_qty_unit:
            flash(
                "In ATTACHED mode, do not enter Total Quantity or Unit. Use only Total Amount.",
                "error",
            )
            return None

    # Build payload according to mode
    if material_mode_raw == "ITEM":
        total_amt = sum(
            (line["amount"] or 0.0)
            for line in lines_data
            if line["amount"] is not None
        )
        header_amount = total_amt if lines_data else None

        material_payload = {
            "mode": "ITEM",
            "total_quantity": None,
            "total_quantity_unit": None,
            "total_amount": header_amount,
            "lines": lines_data,
        }
        return material_payload

    if material_mode_raw == "LUMPSUM":
        if not (has_header_values or has_lines):
            return None

        material_payload = {
            "mode": "LUMPSUM",
            "total_quantity": header_qty,
            "total_quantity_unit": header_qty_unit or None,
            "total_amount": header_amount,
            "lines": lines_data,
        }
        return material_payload

    if material_mode_raw == "ATTACHED":
        # Canonicalize: only header total_amount + one placeholder line
        material_payload = {
            "mode": "ATTACHED",
            "total_quantity": None,
            "total_quantity_unit": None,
            "total_amount": header_amount,
            "lines": [
                {
                    "description": "As per list attached.",
                    "unit": None,
                    "quantity": None,
                    "rate": None,
                    "amount": None,
                }
            ],
        }
        return material_payload

    return None


def _parse_material_block_from_json(block: dict, scope_label: str):
    """
    Parse + validate a single material block coming from JSON.

    Returns normalized block:
      {
        "mode": "ITEM"/"LUMPSUM"/"ATTACHED",
        "total_quantity": float|None,
        "total_quantity_unit": str|None,
        "total_amount": float|None,
        "lines": [ {description, unit, quantity, rate, amount}, ... ]
      }
    """
    if not isinstance(block, dict):
        flash(f"Invalid material block in {scope_label}.", "error")
        return None

    mode = (block.get("mode") or "").strip().upper()
    if mode not in ("ITEM", "LUMPSUM", "ATTACHED"):
        flash(f"Invalid material mode in {scope_label}.", "error")
        return None

    def _to_float(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                return float(s)
            except ValueError:
                return None
        return None

    # ---- headers ----
    header_qty_raw = block.get("total_quantity")
    header_amt_raw = block.get("total_amount")

    header_qty = _to_float(header_qty_raw)
    header_qty_unit = (block.get("total_quantity_unit") or "").strip() or None
    header_amount = _to_float(header_amt_raw)

    # number validation (catch non-empty numeric strings that failed)
    def _is_bad_num(raw):
        return isinstance(raw, str) and raw.strip() and _to_float(raw) is None

    if _is_bad_num(header_qty_raw) or _is_bad_num(header_amt_raw):
        flash(
            f"Invalid number in materials header ({scope_label}). Please check quantity/amount.",
            "error",
        )
        return None

    # ---- lines ----
    lines_in = block.get("lines") or []
    if not isinstance(lines_in, list):
        flash(f"Invalid lines list in {scope_label}.", "error")
        return None

    lines_data = []
    for idx, ln in enumerate(lines_in, start=1):
        if ln is None:
            continue
        if not isinstance(ln, dict):
            flash(f"Invalid line #{idx} in {scope_label}.", "error")
            return None

        desc = (ln.get("description") or "").strip()
        unit = (ln.get("unit") or "").strip() or None

        qty_raw = ln.get("quantity")
        rate_raw = ln.get("rate")
        amt_raw = ln.get("amount")

        qty = _to_float(qty_raw)
        rate = _to_float(rate_raw)
        amount = _to_float(amt_raw)

        # bad numbers in line
        if _is_bad_num(qty_raw) or _is_bad_num(rate_raw) or _is_bad_num(amt_raw):
            flash(
                f"Invalid number in materials lines ({scope_label}). Please check qty/rate/amount.",
                "error",
            )
            return None

        # Entirely empty row → skip
        if not (desc or unit or qty is not None or rate is not None or amount is not None):
            continue

        # Description is mandatory for any non-empty row
        if not desc:
            flash(
                f"Each material row must have a description if any other field is filled ({scope_label}).",
                "error",
            )
            return None

        # Mode-specific line rules
        if mode == "ITEM":
            if (qty is None) ^ (rate is None):
                flash(
                    f"In ITEM mode, each material row must have BOTH Quantity and Rate (or leave both blank) ({scope_label}).",
                    "error",
                )
                return None

            if qty is None and rate is None and amount is not None:
                flash(
                    f"In ITEM mode, do not enter Amount unless Quantity and Rate are provided (Amount is auto-calculated) ({scope_label}).",
                    "error",
                )
                return None

            if qty is not None and rate is not None:
                amount = qty * rate

        elif mode == "ATTACHED":
            if qty is not None or rate is not None or amount is not None:
                flash(
                    f"In ATTACHED mode, do not enter Quantity/Rate/Amount in lines. Use only the header Total Amount ({scope_label}).",
                    "error",
                )
                return None

        # LUMPSUM: allow partial numbers; invariant checked later.

        lines_data.append(
            {
                "description": desc,
                "unit": unit,
                "quantity": qty,
                "rate": rate,
                "amount": amount,
            }
        )

    # -------------------------------------------------
    # Per-mode block-level validations (tightened)
    # -------------------------------------------------
    has_lines = bool(lines_data)

    if mode == "ITEM":
        if not has_lines:
            flash(f"In ITEM mode, enter at least one material line ({scope_label}).", "error")
            return None

        if not any(line.get("amount") is not None for line in lines_data):
            flash(
                f"In ITEM mode, at least one row must include Quantity and Rate so Amount can be computed ({scope_label}).",
                "error",
            )
            return None

        # Derive header total_amount from lines
        total_amt = sum((ln["amount"] or 0.0) for ln in lines_data if ln["amount"] is not None)
        header_amount = total_amt if lines_data else None

        # ITEM never uses header qty/unit
        header_qty = None
        header_qty_unit = None

    elif mode == "LUMPSUM":
        # Tight rule:
        # - must provide a quantity basis either in header OR at least one line qty
        # - amount-only is not sufficient
        has_header_qty = header_qty is not None and header_qty != 0
        has_line_qty = any((ln.get("quantity") is not None and ln.get("quantity") != 0) for ln in lines_data)

        if not has_header_qty and not has_line_qty:
            flash(
                f"In LUMPSUM mode, provide quantity either in the header Total Quantity or in at least one line Quantity ({scope_label}).",
                "error",
            )
            return None

        # Invariant: header qty and line qty cannot both be used
        if has_header_qty and has_line_qty:
            flash(
                f"In LUMPSUM mode, use either the header total quantity or per-line quantities, not both ({scope_label}).",
                "error",
            )
            return None

        # If header qty is used, unit is strongly recommended (optional but you can enforce if you want)
        # if has_header_qty and not header_qty_unit:
        #     flash(f"In LUMPSUM mode, Unit is required when header Total Quantity is used ({scope_label}).", "error")
        #     return None

    elif mode == "ATTACHED":
        if header_amount is None:
            flash(f"In ATTACHED mode, Total Amount is required ({scope_label}).", "error")
            return None

        if header_qty is not None or header_qty_unit:
            flash(
                f"In ATTACHED mode, do not enter Total Quantity or Unit. Use only Total Amount ({scope_label}).",
                "error",
            )
            return None

        # Canonicalize to one placeholder line
        lines_data = [
            {
                "description": "As per list attached.",
                "unit": None,
                "quantity": None,
                "rate": None,
                "amount": None,
            }
        ]
        header_qty = None
        header_qty_unit = None

    return {
        "mode": mode,
        "total_quantity": header_qty,
        "total_quantity_unit": header_qty_unit,
        "total_amount": header_amount,
        "lines": lines_data,
    }

def _parse_material_scopes_from_json(raw_json: str):
    """
    Parse + validate multiscope JSON posted by UI.

    Expected JSON:
      {
        "mode": "AUTHORITY_PAIR",
        "scopes": [
          {
            "from": {"authority_id": <int>},
            "to": {"authority_id": <int>},
            "material": { ...material block... }
          },
          ...
        ]
      }

    Returns:
      {"mode":"AUTHORITY_PAIR","scopes":[...normalized...]}
    """
    try:
        data = json.loads(raw_json)
    except Exception:
        flash("Invalid materials scopes JSON.", "error")
        return None

    mode = (data.get("mode") or "").strip().upper()
    if mode != "AUTHORITY_PAIR":
        flash("Invalid materials scopes mode.", "error")
        return None

    scopes = data.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        flash("Materials: at least one scope is required.", "error")
        return None

    normalized_scopes = []
    for i, s in enumerate(scopes, start=1):
        if not isinstance(s, dict):
            flash(f"Invalid scope entry at #{i}.", "error")
            return None

        frm = s.get("from") or {}
        to = s.get("to") or {}
        block = s.get("material") or {}

        try:
            from_auth_id = int(frm.get("authority_id"))
            to_auth_id = int(to.get("authority_id"))
        except Exception:
            flash(f"Invalid authority id in scope #{i}.", "error")
            return None

        parsed_block = _parse_material_block_from_json(block, scope_label=f"scope #{i}")
        if parsed_block is None:
            return None  # flash already done

        normalized_scopes.append(
            {
                "from": {"authority_id": from_auth_id},
                "to": {"authority_id": to_auth_id},
                "material": parsed_block,
            }
        )

    return {"mode": "AUTHORITY_PAIR", "scopes": normalized_scopes}


def _parse_materials_for_booking():
    """
    Light orchestrator.

    Supports two inputs:
      A) Legacy single/base materials from normal form fields -> uses _parse_materials_from_request()
      B) Multiscope JSON (authority-pair) posted by UI -> uses _parse_material_scopes_from_json()

    Returns a canonical payload dict or None (with flash on error).
    """
    raw_json = (request.form.get("materials_scopes_json") or "").strip()
    if raw_json:
        return _parse_material_scopes_from_json(raw_json)

    material_payload = _parse_materials_from_request()
    if material_payload is None:
        return None

    return {
        "mode": "BASE_BLOCK",
        "per_authority": {None: material_payload},
    }


def _rebuild_material_from_block(
    material: BookingMaterial,
    block: dict,
    sequence_index: int,
) -> None:
    """
    Fill an existing or newly created BookingMaterial from a parsed material block.
    Clears and rebuilds its lines.

    This is used for both creation and edit; on edit we overwrite existing content.
    """
    material.mode = block.get("mode")
    material.sequence_index = sequence_index

    material.total_quantity = block.get("total_quantity")
    material.total_quantity_unit = block.get("total_quantity_unit")
    material.total_amount = block.get("total_amount")

    # Clear existing lines via the relationship collection
    material.lines[:] = []

    lines_data = block.get("lines") or []

    total_amount_from_lines = 0.0
    line_index = 1

    for line_block in lines_data:
        if not line_block:
            continue

        desc = (line_block.get("description") or "").strip()
        if not desc:
            continue

        line = BookingMaterialLine(
            sequence_index=line_index,
            description=desc,
            unit=line_block.get("unit") or None,
            quantity=line_block.get("quantity"),
            rate=line_block.get("rate"),
            amount=line_block.get("amount"),
        )
        material.lines.append(line)
        line_index += 1

        if line.amount is not None:
            try:
                total_amount_from_lines += float(line.amount)
            except (TypeError, ValueError):
                pass

    # For ITEM mode, header total_amount is always derived from lines.
    if material.mode == "ITEM":
        material.total_amount = total_amount_from_lines if material.lines else None


def _compute_route_order_for_booking(booking: Booking) -> dict:
    """
    Return {location_id: sequence_index} for the booking's route, if available.
    Used to ensure FROM comes before TO when building (from, to) pairs.
    """
    route = getattr(booking, "route", None)
    if not route:
        return {}

    order: dict[int, int] = {}
    for rs in route.stops:
        order[rs.location_id] = rs.sequence_index or 0
    return order


def _apply_materials_payload_to_booking(
    booking: Booking,
    loading_bas_unused: list[BookingAuthority],
    materials_payload: dict | None,
    replace_existing: bool = False,
) -> bool:
    """
    Apply materials payload to create/update BookingMaterial tables.

    Returns:
      True  -> applied successfully
      False -> rejected (flash already shown)
    """
    if not materials_payload:
        return True

    payload_mode = (materials_payload.get("mode") or "BASE_BLOCK").upper()

    # ---------------------------------------------------------
    # Multiscope: explicit authority-pair scopes from UI JSON
    # ---------------------------------------------------------
    if payload_mode == "AUTHORITY_PAIR":
        scopes_in = materials_payload.get("scopes") or []
        if not scopes_in:
            flash("Materials scopes JSON is empty.", "error")
            return False

        # Map Authority.id -> BookingAuthority for this booking
        all_bas = list(booking.booking_authorities or [])
        ba_by_authority_id: dict[int, BookingAuthority] = {}
        for ba in all_bas:
            if ba.authority_id is not None:
                ba_by_authority_id[int(ba.authority_id)] = ba

        if not ba_by_authority_id:
            flash("This booking has no authorities; cannot apply scoped materials.", "error")
            return False

        desired_scopes: list[Tuple[Optional[int], Optional[int]]] = []
        block_by_scope: dict[Tuple[Optional[int], Optional[int]], dict] = {}

        invalid_scopes: list[str] = []

        for i, s in enumerate(scopes_in, start=1):
            frm = (s.get("from") or {})
            to = (s.get("to") or {})
            block = (s.get("material") or {})

            try:
                from_auth_id = int(frm.get("authority_id"))
                to_auth_id = int(to.get("authority_id"))
            except Exception:
                invalid_scopes.append(f"scope #{i}: invalid authority_id value(s)")
                continue

            from_ba = ba_by_authority_id.get(from_auth_id)
            to_ba = ba_by_authority_id.get(to_auth_id)

            # Tightening: reject any mismatch instead of silently skipping
            if not from_ba or not to_ba:
                invalid_scopes.append(
                    f"scope #{i}: authority pair ({from_auth_id} → {to_auth_id}) not present in this booking"
                )
                continue

            key = (from_ba.id, to_ba.id)
            desired_scopes.append(key)
            block_by_scope[key] = block

        if invalid_scopes:
            # Show a concise but actionable error
            msg = "Materials scopes JSON contains invalid/mismatched scopes: " + "; ".join(invalid_scopes)
            flash(msg, "error")
            return False

        desired_scopes = list(dict.fromkeys(desired_scopes))
        if not desired_scopes:
            flash("No valid material scopes found to apply.", "error")
            return False

        existing_by_scope: dict[Tuple[Optional[int], Optional[int]], BookingMaterial] = {}
        for m in list(getattr(booking, "material_tables", [])):
            existing_by_scope[(m.booking_authority_id, m.to_booking_authority_id)] = m

        if replace_existing:
            for key, mat in list(existing_by_scope.items()):
                if key not in desired_scopes:
                    db.session.delete(mat)
                    existing_by_scope.pop(key, None)

        seq_counter = 1
        for key in desired_scopes:
            from_id, to_id = key
            material = existing_by_scope.get(key)
            if material is None:
                material = BookingMaterial(
                    booking=booking,
                    booking_authority_id=from_id,
                    to_booking_authority_id=to_id,
                )
                db.session.add(material)
                existing_by_scope[key] = material

            _rebuild_material_from_block(material, block_by_scope[key], sequence_index=seq_counter)
            seq_counter += 1

        return True

    # ---------------------------------------------------------
    # Base-block legacy path
    # ---------------------------------------------------------
    per_auth = materials_payload.get("per_authority") or {}
    base_block = per_auth.get(None)
    if not base_block:
        flash("Missing base material block.", "error")
        return False

    all_bas = list(booking.booking_authorities or [])
    loading_bas = [ba for ba in all_bas if (ba.role or "").upper() == "LOADING"]
    unloading_bas = [ba for ba in all_bas if (ba.role or "").upper() == "UNLOADING"]

    loading_bas.sort(key=lambda ba: ba.sequence_index or 0)
    unloading_bas.sort(key=lambda ba: ba.sequence_index or 0)

    route_order = _compute_route_order_for_booking(booking)

    def _ba_loc_index(ba: BookingAuthority) -> int:
        auth = ba.authority
        loc = getattr(auth, "location", None)
        loc_id = getattr(loc, "id", None)
        if loc_id is None:
            return 10_000 + (ba.sequence_index or 0)
        return route_order.get(loc_id, 10_000 + (ba.sequence_index or 0))

    loading_sorted = sorted(loading_bas, key=_ba_loc_index)
    unloading_sorted = sorted(unloading_bas, key=_ba_loc_index)

    desired_scopes: list[Tuple[Optional[int], Optional[int]]] = []

    if not loading_sorted and not unloading_sorted:
        desired_scopes.append((None, None))
    elif loading_sorted and not unloading_sorted:
        for ba in loading_sorted:
            desired_scopes.append((ba.id, None))
    elif not loading_sorted and unloading_sorted:
        for ba in unloading_sorted:
            desired_scopes.append((None, ba.id))
    else:
        for from_ba in loading_sorted:
            from_idx = _ba_loc_index(from_ba)
            for to_ba in unloading_sorted:
                to_idx = _ba_loc_index(to_ba)
                if from_idx < to_idx:
                    desired_scopes.append((from_ba.id, to_ba.id))

        if not desired_scopes:
            for ba in loading_sorted:
                desired_scopes.append((ba.id, None))

    desired_scopes = list(dict.fromkeys(desired_scopes))

    existing_by_scope: dict[Tuple[Optional[int], Optional[int]], BookingMaterial] = {}
    materials = list(getattr(booking, "material_tables", []))
    for m in materials:
        key = (m.booking_authority_id, m.to_booking_authority_id)
        existing_by_scope[key] = m

    if replace_existing:
        for key, mat in list(existing_by_scope.items()):
            if key not in desired_scopes:
                db.session.delete(mat)
                existing_by_scope.pop(key, None)

    seq_counter = 1
    for from_id, to_id in desired_scopes:
        key = (from_id, to_id)
        material = existing_by_scope.get(key)

        if material is None:
            material = BookingMaterial(
                booking=booking,
                booking_authority_id=from_id,
                to_booking_authority_id=to_id,
            )
            db.session.add(material)
            existing_by_scope[key] = material

        _rebuild_material_from_block(material, base_block, sequence_index=seq_counter)
        seq_counter += 1

    return True

def _create_booking_core(
    from_codes,
    dest_codes,
    trip_km: int,
    placement_date: date,
    booking_date: date,
    lorry_id: int,
    materials_payload: dict | None,
    remarks_prefix: str | None = None,
):
    """
    Shared core logic for creating a Booking (normal or backdated).

    On error: flashes messages and returns None.
    On success: commits and returns the Booking instance.
    """
    lorry = LorryDetails.query.get(lorry_id)
    if not lorry:
        flash("Selected lorry does not exist.", "error")
        return None

    active_agreement = Agreement.query.filter_by(is_active=True).first()
    if not active_agreement:
        flash(
            "No active agreement found. Please activate an agreement before creating a booking.",
            "error",
        )
        return None

    seq_codes = from_codes + dest_codes
    if len(seq_codes) < 2:
        flash("Route must contain at least two locations.", "error")
        return None

    seen = set()
    duplicates = []
    for c in seq_codes:
        if c in seen and c not in duplicates:
            duplicates.append(c)
        seen.add(c)
    if duplicates:
        dup_str = ", ".join(duplicates)
        flash(
            f"Each location can appear only once in a booking route. Duplicates: {dup_str}.",
            "error",
        )
        return None

    locations = []
    missing_codes = []
    code_to_location = {}

    for code in seq_codes:
        if code in code_to_location:
            loc = code_to_location[code]
        else:
            loc = Location.query.filter_by(code=code).first()
            if not loc:
                missing_codes.append(code)
                continue
            code_to_location[code] = loc
        locations.append(loc)

    if missing_codes:
        human = ", ".join(sorted(set(missing_codes)))
        flash(f"Unknown location code(s): {human}.", "error")
        return None

    missing_loading = []
    for code in from_codes:
        auth_ids = request.form.getlist(f"loading_{code}[]")
        if not auth_ids:
            missing_loading.append(code)

    missing_unloading = []
    for code in dest_codes:
        auth_ids = request.form.getlist(f"unloading_{code}[]")
        if not auth_ids:
            missing_unloading.append(code)

    if missing_loading or missing_unloading:
        msgs = []
        if missing_loading:
            msgs.append(
                "Select at least one loading authority for each FROM location "
                f"(missing for: {', '.join(sorted(set(missing_loading)))})."
            )
        if missing_unloading:
            msgs.append(
                "Select at least one unloading authority for each DESTINATION location "
                f"(missing for: {', '.join(sorted(set(missing_unloading)))})."
            )
        flash(" ".join(msgs), "error")
        return None

    all_codes = [loc.code for loc in locations]
    first_code = all_codes[0]
    last_code = all_codes[-1]
    mid_codes = all_codes[1:-1]

    route_code, route_name = build_route_code_and_name(
        [first_code],
        mid_codes,
        [last_code],
        trip_km,
    )

    route = Route.query.filter_by(code=route_code).first()
    if route:
        if route.total_km != trip_km:
            flash(
                f"Existing route {route.code} has total distance {route.total_km} KM, "
                f"but you entered {trip_km} KM. Please use the same distance or adjust the route.",
                "error",
            )
            return None
    else:
        route = Route(
            code=route_code,
            name=route_name,
            total_km=trip_km,
        )
        db.session.add(route)
        db.session.flush()

        for idx, loc in enumerate(locations, start=1):
            stop = RouteStop(
                route_id=route.id,
                location_id=loc.id,
                sequence_index=idx,
                is_start_cluster=(idx == 1),
                is_end_cluster=(idx == len(locations)),
            )
            db.session.add(stop)

    remarks_value = remarks_prefix if remarks_prefix else None

    booking = Booking(
        agreement_id=active_agreement.id,
        company_id=active_agreement.company_id,
        lorry_id=lorry.id,
        route_id=route.id,
        trip_km=trip_km,
        placement_date=placement_date,
        booking_date=booking_date,
        remarks=remarks_value,
    )
    db.session.add(booking)
    db.session.flush()

    loading_seq = 1
    for code in from_codes:
        auth_ids = request.form.getlist(f"loading_{code}[]")
        for aid in auth_ids:
            try:
                aid_int = int(aid)
            except (TypeError, ValueError):
                continue

            ba = BookingAuthority(
                booking_id=booking.id,
                authority_id=aid_int,
                role="LOADING",
                sequence_index=loading_seq,
            )
            db.session.add(ba)
            loading_seq += 1

    unloading_seq = 1
    for code in dest_codes:
        auth_ids = request.form.getlist(f"unloading_{code}[]")
        for aid in auth_ids:
            try:
                aid_int = int(aid)
            except (TypeError, ValueError):
                continue

            ba = BookingAuthority(
                booking_id=booking.id,
                authority_id=aid_int,
                role="UNLOADING",
                sequence_index=unloading_seq,
            )
            db.session.add(ba)
            unloading_seq += 1

    db.session.flush()

    ok = _apply_materials_payload_to_booking(
        booking,
        loading_bas_unused=[],
        materials_payload=materials_payload,
        replace_existing=False,
    )

    if not ok:
        db.session.rollback()
        return None

    db.session.commit()
    return booking


@admin_bp.route("/booking/add", methods=["POST"])
def add_booking():
    from_codes_raw = request.form.getlist("from_locations[]")
    dest_codes_raw = request.form.getlist("dest_locations[]")

    from_codes = _normalize_codes(from_codes_raw)
    dest_codes = _normalize_codes(dest_codes_raw)

    errors = []

    if not from_codes:
        errors.append("Add at least one FROM location.")
    if not dest_codes:
        errors.append("Add at least one DESTINATION location.")

    placement_raw = (request.form.get("placement_date") or "").strip()
    placement_date = None
    today = date.today()

    if not placement_raw:
        errors.append("Placement date is required.")
    else:
        try:
            placement_date = datetime.strptime(placement_raw, "%Y-%m-%d").date()
            if placement_date < today:
                errors.append("Placement date cannot be earlier than the booking date.")
        except ValueError:
            errors.append("Invalid placement date.")

    trip_km = request.form.get("trip_km", type=int)
    lorry_id = request.form.get("lorry_id", type=int)

    if trip_km is None or trip_km <= 0:
        errors.append("Distance (KM) must be a positive integer.")
    if not lorry_id:
        errors.append("Select a lorry.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_to_tab("#booking")

    materials_payload = _parse_materials_for_booking()
    if materials_payload is None:
        return _redirect_to_tab("#booking")

    booking_date = today

    booking = _create_booking_core(
        from_codes=from_codes,
        dest_codes=dest_codes,
        trip_km=trip_km,
        placement_date=placement_date,
        booking_date=booking_date,
        lorry_id=lorry_id,
        materials_payload=materials_payload,
        remarks_prefix=None,
    )

    if booking is None:
        return _redirect_to_tab("#booking")

    flash("Booking saved successfully.", "success")
    return _redirect_to_tab("#booking")


@admin_bp.route("/booking/backdated", methods=["GET"])
def backdated_booking_view():
    lorries = LorryDetails.query.order_by(LorryDetails.capacity).all()
    all_locations = Location.query.order_by(Location.name).all()

    booking_auth_map = {}
    authorities = Authority.query.all()

    for auth in authorities:
        code = auth.location.code
        if code not in booking_auth_map:
            booking_auth_map[code] = []
        booking_auth_map[code].append(
            {
                "id": auth.id,
                "title": auth.authority_title,
                "address": auth.address,
            }
        )

    for code in booking_auth_map:
        booking_auth_map[code].sort(key=lambda x: x["title"].lower())

    return render_template(
        "admin/backdated_booking.html",
        lorries=lorries,
        all_locations=all_locations,
        booking_auth_map=booking_auth_map,
    )


@admin_bp.route("/booking/backdated-add", methods=["POST"])
def add_backdated_booking():
    from_codes_raw = request.form.getlist("from_locations[]")
    dest_codes_raw = request.form.getlist("dest_locations[]")

    from_codes = _normalize_codes(from_codes_raw)
    dest_codes = _normalize_codes(dest_codes_raw)

    errors = []

    if not from_codes:
        errors.append("Add at least one FROM location.")
    if not dest_codes:
        errors.append("Add at least one DESTINATION location.")

    today = date.today()

    booking_raw = (request.form.get("booking_date") or "").strip()
    placement_raw = (request.form.get("placement_date") or "").strip()
    reason = (request.form.get("backdated_reason") or "").strip()

    booking_date = None
    placement_date = None

    if not booking_raw:
        errors.append("Booking date is required for backdated entries.")
    else:
        try:
            booking_date = datetime.strptime(booking_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Invalid booking date.")

    if not placement_raw:
        errors.append("Placement date is required.")
    else:
        try:
            placement_date = datetime.strptime(placement_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Invalid placement date.")

    if booking_date and booking_date > today:
        errors.append("Booking date cannot be in the future.")
    if placement_date and placement_date > today:
        errors.append("Placement date cannot be in the future.")
    if booking_date and placement_date and placement_date < booking_date:
        errors.append("Placement date cannot be earlier than the booking date.")

    if not reason:
        errors.append("Reason for backdated booking is required.")

    trip_km = request.form.get("trip_km", type=int)
    lorry_id = request.form.get("lorry_id", type=int)

    if trip_km is None or trip_km <= 0:
        errors.append("Distance (KM) must be a positive integer.")
    if not lorry_id:
        errors.append("Select a lorry.")

    if errors:
        flash(" ".join(errors), "error")
        return _redirect_to_tab("#booking")

    materials_payload = _parse_materials_for_booking()
    if materials_payload is None:
        return _redirect_to_tab("#booking")

    remarks_prefix = f"[BACKDATED] {reason}"

    booking = _create_booking_core(
        from_codes=from_codes,
        dest_codes=dest_codes,
        trip_km=trip_km,
        placement_date=placement_date,
        booking_date=booking_date,
        lorry_id=lorry_id,
        materials_payload=materials_payload,
        remarks_prefix=remarks_prefix,
    )

    if booking is None:
        return _redirect_to_tab("#booking")

    flash("Backdated booking recorded successfully.", "success")
    return _redirect_to_tab("#booking")


def _serialize_material_table(material: BookingMaterial) -> dict:
    if material is None:
        return {
            "mode": None,
            "header": None,
            "lines": [],
        }

    lines_payload = []
    for line in material.lines:
        lines_payload.append(
            {
                "sequence_index": line.sequence_index,
                "description": line.description,
                "unit": line.unit,
                "quantity": line.quantity,
                "rate": line.rate,
                "amount": line.amount,
            }
        )

    header_payload = {
        "total_quantity": material.total_quantity,
        "total_quantity_unit": material.total_quantity_unit,
        "total_amount": material.total_amount,
    }

    return {
        "mode": material.mode,
        "header": header_payload,
        "lines": lines_payload,
    }


@admin_bp.route("/booking/<int:booking_id>/materials-json", methods=["GET"])
def booking_materials_json(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)

    tables = list(getattr(booking, "material_tables", [])) or []
    if len(tables) == 0:
        return jsonify(
            {
                "success": True,
                "has_materials": False,
                "mode": None,
                "header": None,
                "lines": [],
                "note": "No material tables found.",
            }
        )

    # Legacy endpoint: if multiscope is present, tell client to use the richer endpoint
    if len(tables) > 1:
        return jsonify(
            {
                "success": True,
                "has_materials": True,
                "is_multiscope": True,
                "note": "Use /materials-per-authority-json for multiscope materials.",
            }
        )

    serialized = _serialize_material_table(tables[0])
    return jsonify(
        {
            "success": True,
            "has_materials": True,
            "is_multiscope": False,
            "mode": serialized["mode"],
            "header": serialized["header"],
            "lines": serialized["lines"],
        }
    )

@admin_bp.route("/booking/<int:booking_id>/materials-per-authority-json", methods=["GET"])
def booking_materials_per_authority_json(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)

    materials = list(getattr(booking, "material_tables", []))

    mats_by_from_ba: dict[int | None, list[BookingMaterial]] = {}
    for m in materials:
        key = m.booking_authority_id
        mats_by_from_ba.setdefault(key, []).append(m)

    def authority_payload(ba: BookingAuthority | None):
        if ba is None:
            return None
        auth = ba.authority
        loc = auth.location if auth else None
        return {
            "id": auth.id if auth else None,
            "title": auth.authority_title if auth else None,
            "address": auth.address if auth else None,
            "location_code": loc.code if loc else None,
            "location_name": loc.name if loc else None,
        }

    booking_level = []
    for m in mats_by_from_ba.get(None, []):
        if m.to_booking_authority_id is not None:
            continue
        payload = _serialize_material_table(m)
        booking_level.append(
            {
                "booking_material_id": m.id,
                "booking_authority_id": None,
                "to_booking_authority_id": None,
                "sequence_index": m.sequence_index,
                "role": "BOOKING",
                "authority": None,
                "from_authority": None,
                "to_authority": None,
                "mode": payload["mode"],
                "header": payload["header"],
                "lines": payload["lines"],
            }
        )

    loading = []
    unloading = []

    for ba in booking.booking_authorities:
        role = (ba.role or "").upper()
        mats_for_from_ba = mats_by_from_ba.get(ba.id, [])

        for m in mats_for_from_ba:
            payload = _serialize_material_table(m)
            from_auth = authority_payload(ba)
            to_auth = authority_payload(m.to_booking_authority)

            block = {
                "booking_material_id": m.id,
                "booking_authority_id": ba.id,
                "to_booking_authority_id": m.to_booking_authority_id,
                "sequence_index": m.sequence_index,
                "role": role,
                "authority": from_auth,
                "from_authority": from_auth,
                "to_authority": to_auth,
                "mode": payload["mode"],
                "header": payload["header"],
                "lines": payload["lines"],
            }

            if role == "LOADING":
                loading.append(block)
            elif role == "UNLOADING":
                unloading.append(block)

        for m in materials:
            if m.booking_authority_id is None and m.to_booking_authority_id == ba.id:
                payload = _serialize_material_table(m)
                to_auth = authority_payload(ba)
                block = {
                    "booking_material_id": m.id,
                    "booking_authority_id": None,
                    "to_booking_authority_id": ba.id,
                    "sequence_index": m.sequence_index,
                    "role": "UNLOADING",
                    "authority": to_auth,
                    "from_authority": None,
                    "to_authority": to_auth,
                    "mode": payload["mode"],
                    "header": payload["header"],
                    "lines": payload["lines"],
                }
                unloading.append(block)

    from_to = []

    for m in materials:
        if m.booking_authority_id is None and m.to_booking_authority_id is None:
            continue

        from_ba = m.booking_authority
        to_ba = m.to_booking_authority

        payload = _serialize_material_table(m)
        from_auth = authority_payload(from_ba)
        to_auth = authority_payload(to_ba)

        from_to.append(
            {
                "booking_material_id": m.id,
                "sequence_index": m.sequence_index,
                "from_ba_id": m.booking_authority_id,
                "to_ba_id": m.to_booking_authority_id,
                "from_role": (from_ba.role if from_ba and from_ba.role else None),
                "to_role": (to_ba.role if to_ba and to_ba.role else None),
                "from_authority": from_auth,
                "to_authority": to_auth,
                "mode": payload["mode"],
                "header": payload["header"],
                "lines": payload["lines"],
            }
        )

    loading.sort(key=lambda x: x["sequence_index"])
    unloading.sort(key=lambda x: x["sequence_index"])
    booking_level.sort(key=lambda x: x["sequence_index"])
    from_to.sort(key=lambda x: x["sequence_index"])

    return jsonify(
        {
            "success": True,
            "booking_id": booking.id,
            "booking_level": booking_level,
            "loading": loading,
            "unloading": unloading,
            "from_to": from_to,
        }
    )


@admin_bp.route("/booking/<int:booking_id>/cancel", methods=["POST"])
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    redirect_tab = request.form.get("redirect_tab") or "#booking"
    booking_scope = (request.form.get("booking_scope") or "").strip()
    booking_status = (request.form.get("booking_status") or "").strip()
    booking_search = (request.form.get("booking_search") or "").strip()

    def _redirect_after_cancel():
        if redirect_tab == "#history":
            params = {}
            if booking_scope:
                params["booking_scope"] = booking_scope
            if booking_status:
                params["booking_status"] = booking_status
            if booking_search:
                params["booking_search"] = booking_search
            return redirect(url_for("admin.dashboard", **params) + redirect_tab)
        return _redirect_to_tab(redirect_tab)

    if booking.status == "CANCELLED":
        flash("Booking already cancelled.", "info")
        return _redirect_after_cancel()

    reason = (request.form.get("cancel_reason") or "").strip() or None

    booking.status = "CANCELLED"
    booking.cancelled_at = datetime.utcnow()
    booking.cancel_reason = reason

    db.session.commit()
    flash(f"Booking {booking.id} cancelled.", "success")

    return _redirect_after_cancel()


@admin_bp.route("/booking/<int:booking_id>", methods=["GET", "POST"])
def booking_detail(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    def _redirect_self_with_filters():
        params = {
            "booking_id": booking.id,
            "booking_scope": request.args.get("booking_scope"),
            "booking_status": request.args.get("booking_status"),
            "booking_search": request.args.get("booking_search"),
        }
        params = {k: v for k, v in params.items() if v}
        return redirect(url_for("admin.booking_detail", **params))

    if booking.status == "CANCELLED" and request.method == "POST":
        flash("Cancelled bookings cannot be edited.", "error")
        return _redirect_self_with_filters()

    lorries = LorryDetails.query.order_by(LorryDetails.capacity).all()

    if request.method == "POST":
        errors: list[str] = []

        placement_raw = (request.form.get("placement_date") or "").strip()
        placement_date = None
        if not placement_raw:
            errors.append("Placement date is required.")
        else:
            try:
                placement_date = datetime.strptime(placement_raw, "%Y-%m-%d").date()
                if placement_date < booking.booking_date:
                    errors.append("Placement date cannot be earlier than the booking date.")
            except ValueError:
                errors.append("Invalid placement date.")

        lorry_id = request.form.get("lorry_id", type=int)
        lorry = None
        if not lorry_id:
            errors.append("Select a lorry.")
        else:
            lorry = LorryDetails.query.get(lorry_id)
            if not lorry:
                errors.append("Selected lorry does not exist.")

        if errors:
            for msg in errors:
                flash(msg, "error")
        else:
            booking.placement_date = placement_date
            booking.lorry_id = lorry.id
            db.session.commit()
            flash("Booking updated successfully.", "success")
            return _redirect_self_with_filters()

    siblings = (
        Booking.query.filter_by(agreement_id=booking.agreement_id)
        .order_by(Booking.id.asc())
        .all()
    )

    trip_serial = None
    for idx, b in enumerate(siblings, start=1):
        if b.id == booking.id:
            trip_serial = idx
            break

    material = getattr(booking, "material_table", None)

    return render_template(
        "admin/booking_detail.html",
        booking=booking,
        material=material,
        lorries=lorries,
        trip_serial=trip_serial,
    )


def _parse_materials_from_edit_form(mode: str):
    """
    Parse and validate materials from the booking detail edit form.

    Supports modes: ITEM, LUMPSUM, ATTACHED.

    ATTACHED rules (edit):
      - Total Amount required
      - No header quantity/unit
      - No qty/rate/amount in lines
      - Store a single placeholder line: "As per list attached."
    """
    if mode not in ("ITEM", "LUMPSUM", "ATTACHED"):
        flash("Invalid material mode.", "error")
        return None

    def parse_float(form_name: str):
        raw = request.form.get(form_name)
        if raw is None:
            return None
        raw = raw.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    # -------------------------------
    # ATTACHED: ignore UI noise early
    # -------------------------------
    if mode == "ATTACHED":
        header_amount = parse_float("material_total_amount")
        if header_amount is None:
            flash("In ATTACHED mode, Total Amount is required.", "error")
            return None

        return {
            "mode": "ATTACHED",
            "total_quantity": None,
            "total_quantity_unit": None,
            "total_amount": header_amount,
            "lines": [
                {
                    "description": "As per list attached.",
                    "unit": None,
                    "quantity": None,
                    "rate": None,
                    "amount": None,
                }
            ],
        }

    header_qty = None
    header_qty_unit = None
    if mode == "LUMPSUM":
        header_qty = parse_float("material_total_quantity")
        total_unit_raw = (request.form.get("material_total_quantity_unit") or "").strip()
        header_qty_unit = total_unit_raw or None

    header_amount = parse_float("material_total_amount")

    desc_list = request.form.getlist("line_description[]")
    unit_list = request.form.getlist("line_unit[]")
    qty_list = request.form.getlist("line_quantity[]")
    rate_list = request.form.getlist("line_rate[]")
    amt_list = request.form.getlist("line_amount[]")

    def list_float(values, idx):
        if idx >= len(values):
            return None
        raw = (values[idx] or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    lines_data = []
    has_line_qty = False
    has_any_line = False

    for i, desc in enumerate(desc_list):
        desc = (desc or "").strip()
        if not desc:
            continue

        unit_val = (unit_list[i] if i < len(unit_list) else "") or ""
        unit_val = unit_val.strip() or None

        qty_val = list_float(qty_list, i)
        rate_val = list_float(rate_list, i)
        amt_val = list_float(amt_list, i)

        if qty_val is not None:
            has_line_qty = True

        if mode == "ITEM":
            if (qty_val is None) ^ (rate_val is None):
                flash(
                    "In ITEM mode, each material row must have BOTH Quantity and Rate (or leave both blank).",
                    "error",
                )
                return None

            if qty_val is None and rate_val is None and amt_val is not None:
                flash(
                    "In ITEM mode, do not enter Amount unless Quantity and Rate are provided (Amount is auto-calculated).",
                    "error",
                )
                return None

            if qty_val is not None and rate_val is not None:
                amt_val = qty_val * rate_val

        lines_data.append(
            {
                "description": desc,
                "unit": unit_val,
                "quantity": qty_val,
                "rate": rate_val,
                "amount": amt_val,
            }
        )
        has_any_line = True

    if mode == "ITEM":
        if not has_any_line:
            flash("In ITEM mode, enter at least one material line.", "error")
            return None

        if not any(ln.get("amount") is not None for ln in lines_data):
            flash(
                "In ITEM mode, at least one row must include Quantity and Rate so Amount can be computed.",
                "error",
            )
            return None

        total_amt = sum((ln["amount"] or 0.0) for ln in lines_data if ln["amount"] is not None)
        header_amount = total_amt if lines_data else None
        header_qty = None
        header_qty_unit = None

    elif mode == "LUMPSUM":
        has_header_values = bool(header_qty is not None or header_amount is not None or header_qty_unit)
        has_lines = has_any_line

        if not has_header_values and not has_lines:
            flash(
                "In LUMPSUM mode, enter a header quantity/amount or at least one material line.",
                "error",
            )
            return None

        has_header_qty = header_qty is not None
        if has_header_qty and has_line_qty:
            flash(
                "In LUMPSUM mode, use either the header total quantity or per-line quantities, not both.",
                "error",
            )
            return None

    return {
        "mode": mode,
        "total_quantity": header_qty,
        "total_quantity_unit": header_qty_unit,
        "total_amount": header_amount,
        "lines": lines_data,
    }


@admin_bp.route("/booking/<int:booking_id>/materials-edit", methods=["POST"])
def booking_materials_edit(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)

    if booking.status == "CANCELLED":
        flash("Cancelled bookings cannot be edited.", "error")
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    # If UI posts multiscope JSON, prefer that
    raw_scopes_json = (request.form.get("materials_scopes_json") or "").strip()

    if raw_scopes_json:
        materials_payload = _parse_material_scopes_from_json(raw_scopes_json)
        if materials_payload is None:
            return redirect(url_for("admin.booking_detail", booking_id=booking.id))

        ok = _apply_materials_payload_to_booking(
            booking,
            loading_bas_unused=[],
            materials_payload=materials_payload,   # mode=AUTHORITY_PAIR
            replace_existing=True,                 # true edit semantics
        )
        if not ok:
            db.session.rollback()
            return redirect(url_for("admin.booking_detail", booking_id=booking.id))

        db.session.commit()
        flash("Scoped material tables saved.", "success")
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    # -------------------------
    # Legacy single-block edit
    # -------------------------
    mode = (request.form.get("material_mode") or "").strip().upper()

    if not mode:
        flash(
            "Each booking must include a material list. "
            "Choose ITEM, LUMPSUM, or ATTACHED and enter the required fields",
            "error",
        )
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    if mode not in ("ITEM", "LUMPSUM", "ATTACHED"):
        flash("Invalid material mode.", "error")
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    block = _parse_materials_from_edit_form(mode)
    if block is None:
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    materials_payload = {
        "mode": "BASE_BLOCK",
        "per_authority": {None: block},
    }

    ok = _apply_materials_payload_to_booking(
        booking,
        loading_bas_unused=[],
        materials_payload=materials_payload,
        replace_existing=True,
    )

    if not ok:
        db.session.rollback()
        return redirect(url_for("admin.booking_detail", booking_id=booking.id))

    db.session.commit()
    flash("Material list saved.", "success")
    return redirect(url_for("admin.booking_detail", booking_id=booking.id))

@admin_bp.route("/route-km-json", methods=["GET"])
def route_km_json():
    from_code = (request.args.get("from") or "").strip().upper()
    to_code = (request.args.get("to") or "").strip().upper()

    if not from_code or not to_code:
        return jsonify({"options": []})

    from_loc = Location.query.filter_by(code=from_code).first()
    to_loc = Location.query.filter_by(code=to_code).first()

    if not from_loc or not to_loc:
        return jsonify({"options": []})

    routes = Route.query.filter_by(is_active=True).all()

    km_options = []

    for r in routes:
        start_codes = [s.location.code for s in r.stops if s.is_start_cluster]
        end_codes = [s.location.code for s in r.stops if s.is_end_cluster]

        ok_1 = from_code in start_codes and to_code in end_codes
        ok_2 = to_code in start_codes and from_code in end_codes

        if ok_1 or ok_2:
            km_options.append(
                {
                    "km": r.total_km,
                    "route_code": r.code,
                    "route_name": r.name,
                }
            )

    seen = set()
    unique = []
    for opt in km_options:
        key = (opt["km"], opt["route_code"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(opt)

    return jsonify({"options": unique})
