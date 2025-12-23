# admin/letters.py  (WORK IN PROGRESS - refactor wiring to transport/letters/)
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from flask import (
    request,
    redirect,
    url_for,
    flash,
    render_template,
    send_file,
)
from werkzeug.utils import secure_filename

from transport.models import (
    db,
    Booking,
    BookingLetter,
    BookingLetterAttachment,
)

from . import admin_bp

# --- Letters modules (new refactor tree) ---
from transport.letters import (
    # signatories
    get_active_letter_signatories,
    get_signatory_by_id,
    # snapshots + hashing
    build_snapshot,
    build_canonical_snapshot_for_placement,
    hash_canonical_snapshot,
    booking_requires_attachment_pdf,
    # storage
    booking_letters_dir,
    next_letter_sequence,
    merge_pdfs,
    # pdf generators
    generate_placement_advice_pdf,
    generate_modification_advice_pdf,
)

from transport.letters.pdf_modification import compute_mod_diff
from transport.letters.storage import is_pdf_filename, clean_filename_keep_spaces


# =============================================================================
# Redirect helpers (preserve dashboard scope/status/search context)
# =============================================================================

def _ctx_from_request() -> Dict[str, str]:
    """
    Preserve dashboard filter/scope/search context across POST redirects.
    Pattern A: values posted as hidden inputs; fallback to query args.
    """
    scope = (request.form.get("booking_scope") or request.args.get("booking_scope") or "").strip()
    status = (request.form.get("booking_status") or request.args.get("booking_status") or "").strip()
    search = (request.form.get("booking_search") or request.args.get("booking_search") or "").strip()

    ctx: Dict[str, str] = {}
    if scope:
        ctx["booking_scope"] = scope
    if status:
        ctx["booking_status"] = status
    if search:
        ctx["booking_search"] = search
    return ctx


def _redirect_booking_detail(booking_id: int):
    ctx = _ctx_from_request()
    return redirect(url_for("admin.booking_detail", booking_id=booking_id, **ctx))


def _redirect_letters_page(booking_id: int):
    ctx = _ctx_from_request()
    return redirect(url_for("admin.generate_placement_advice", booking_id=booking_id, **ctx))


# =============================================================================
# Local-only helpers (kept here for now)
# =============================================================================

def _booking_date_default(booking: Booking) -> date:
    """
    Requirement: default letter date should be Booking Date (not placement date).
    """
    bd = getattr(booking, "booking_date", None)
    return bd if isinstance(bd, date) else date.today()


def _modification_date_default() -> date:
    """
    Requirement: Modification Advice default date is TODAY.
    """
    return date.today()


def _find_existing_mod_for_hash(booking_id: int, content_hash: str) -> Optional[BookingLetter]:
    """
    If we've already generated a PLACEMENT_MOD for this exact current state (content_hash),
    reuse it (serve the existing PDF) instead of generating another MOD.
    """
    mods = (
        BookingLetter.query
        .filter_by(booking_id=booking_id, letter_type="PLACEMENT_MOD")
        .order_by(BookingLetter.sequence_no.desc())
        .all()
    )
    for m in mods:
        snap = (m.snapshot_json or {})
        if snap.get("content_hash") == content_hash:
            return m
    return None


def _download_name_for_placement(snapshot: Dict[str, Any]) -> str:
    """
    Keep your earlier nice download naming ("trip - FROM to TO on date.pdf").
    We keep it local for now (can be moved into transport/letters/storage later).
    """
    booking: Booking = snapshot["booking"]
    trip_serial: int = snapshot["trip_serial"]

    loading = snapshot.get("loading") or []
    unloading = snapshot.get("unloading") or []

    def _loc_label(ba) -> str:
        try:
            if ba and ba.authority and ba.authority.location:
                code = (ba.authority.location.code or "").strip()
                if code:
                    return code
            if ba and ba.authority:
                return (ba.authority.authority_title or "").strip() or "AUTH"
        except Exception:
            pass
        return "AUTH"

    from_str = " ".join([_loc_label(ba) for ba in loading if ba]).strip() or "FROM"
    to_str = " ".join([_loc_label(ba) for ba in unloading if ba]).strip() or "TO"

    placement_dt = (
        booking.placement_date.strftime("%d-%m-%Y")
        if booking.placement_date
        else snapshot["letter_date"].strftime("%d-%m-%Y")
    )

    raw = f"{trip_serial} - {from_str} to {to_str} on {placement_dt}.pdf"
    return clean_filename_keep_spaces(raw)


# =============================================================================
# Route: Placement Advice + Modification Advice (auto change detection)
# =============================================================================

@admin_bp.route("/letters/placement/<int:booking_id>", methods=["GET", "POST"])
def generate_placement_advice(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)

    letter_type_base = "PLACEMENT"

    baseline_letter = (
        BookingLetter.query
        .filter_by(booking_id=booking.id, letter_type=letter_type_base)
        .order_by(BookingLetter.sequence_no.asc())
        .first()
    )

    if getattr(booking, "is_cancelled", False):
        flash("Cannot generate Placement Advice for a CANCELLED booking.", "error")
        return _redirect_booking_detail(booking.id)

    requires_attachment = booking_requires_attachment_pdf(booking)

    # ---------------------------------------------------------------------
    # GET: UI + downloads
    # ---------------------------------------------------------------------
    if request.method == "GET":
        baseline_has_snapshot = False
        changes_detected = False
        existing_mod_letter: Optional[BookingLetter] = None

        # Download issued baseline PDF
        if request.args.get("download") == "1":
            if not baseline_letter or not baseline_letter.pdf_path:
                flash("No issued Placement Advice PDF found for this booking.", "error")
                return _redirect_letters_page(booking.id)

            pdf_path = Path(baseline_letter.pdf_path)
            if not pdf_path.exists():
                flash("Issued Placement Advice PDF is missing from storage.", "error")
                return _redirect_letters_page(booking.id)

            return send_file(
                str(pdf_path),
                as_attachment=True,
                download_name=clean_filename_keep_spaces(pdf_path.name),
                mimetype="application/pdf",
            )

        # Compute hash state (only if baseline snapshot exists)
        if baseline_letter and baseline_letter.snapshot_json:
            base_canon = (baseline_letter.snapshot_json or {}).get("canonical")
            base_hash_stored = (baseline_letter.snapshot_json or {}).get("content_hash")
            baseline_has_snapshot = bool(base_canon and base_hash_stored)

            if baseline_has_snapshot:
                base_hash = hash_canonical_snapshot(base_canon)
                current_canon = build_canonical_snapshot_for_placement(booking, date.today())
                current_hash = hash_canonical_snapshot(current_canon)
                changes_detected = (current_hash != base_hash)

                if changes_detected:
                    existing_mod_letter = _find_existing_mod_for_hash(booking.id, current_hash)

        # Download MOD (prefer the one matching current state)
        if request.args.get("download_mod") == "1":
            mod_to_send = existing_mod_letter
            if mod_to_send is None:
                mod_to_send = (
                    BookingLetter.query
                    .filter_by(booking_id=booking.id, letter_type="PLACEMENT_MOD")
                    .order_by(BookingLetter.sequence_no.desc())
                    .first()
                )

            if not mod_to_send or not mod_to_send.pdf_path:
                flash("No Modification Advice PDF found for this booking.", "error")
                return _redirect_letters_page(booking.id)

            mod_path = Path(mod_to_send.pdf_path)
            if not mod_path.exists():
                flash("Modification Advice PDF is missing from storage.", "error")
                return _redirect_letters_page(booking.id)

            return send_file(
                str(mod_path),
                as_attachment=True,
                download_name=clean_filename_keep_spaces(f"MOD - {mod_path.name}"),
                mimetype="application/pdf",
            )

        # Default date:
        # - baseline screen => booking_date
        # - modification screen (baseline exists + changes detected) => today()
        default_letter_date = (
            _modification_date_default().isoformat()
            if (baseline_letter and changes_detected)
            else _booking_date_default(booking).isoformat()
        )

        # UI decision: allow generating MOD only if changed AND no existing MOD for current hash
        can_generate_mod = bool(baseline_letter and changes_detected and existing_mod_letter is None)

        signatories = get_active_letter_signatories()

        return render_template(
            "admin/letters/placement_advice.html",
            booking=booking,
            requires_attachment=(requires_attachment and baseline_letter is None),
            default_letter_date=default_letter_date,
            baseline_letter=baseline_letter,
            baseline_has_snapshot=baseline_has_snapshot,
            changes_detected=changes_detected,
            existing_mod_letter=existing_mod_letter,
            can_generate_mod=can_generate_mod,
            signatories=signatories,
        )

    # ---------------------------------------------------------------------
    # POST: issue baseline or MOD (or serve existing)
    # ---------------------------------------------------------------------
    letter_date_str = (request.form.get("letter_date") or "").strip()
    try:
        # For baseline issuance, empty date uses booking_date default.
        # For mod issuance, UI sends today's date by default anyway.
        letter_date_val = date.fromisoformat(letter_date_str) if letter_date_str else _booking_date_default(booking)
    except ValueError:
        flash("Invalid letter date.", "error")
        return _redirect_letters_page(booking.id)

    uploaded_path: Optional[Path] = None
    original_name: Optional[str] = None

    # Attachment required only for first baseline if ATTACHED materials exist
    if requires_attachment and baseline_letter is None:
        f = request.files.get("attachment_pdf")
        if not f or not f.filename:
            flash("Attachment PDF is required because materials are in ATTACHED mode.", "error")
            return _redirect_letters_page(booking.id)
        if not is_pdf_filename(f.filename):
            flash("Attachment must be a PDF file.", "error")
            return _redirect_letters_page(booking.id)

    # -------------------------------------------------------------
    # Letter Signatory selection (Signed by / Signed for)
    # -------------------------------------------------------------
    signed_by_id = (request.form.get("signed_by_id") or "").strip()
    signed_for_id = (request.form.get("signed_for_id") or "").strip()

    signed_by = get_signatory_by_id(signed_by_id)
    signed_for = get_signatory_by_id(signed_for_id)

    # Optional strict validation (recommended): if UI sends ids, they must exist.
    # If you want to allow empty (fallback to legacy hardcoded), keep as-is.
    if signed_by_id and not signed_by:
        flash("Invalid 'Letter signed by' selection.", "error")
        return _redirect_letters_page(booking.id)

    if signed_for_id and not signed_for:
        flash("Invalid 'For' selection.", "error")
        return _redirect_letters_page(booking.id)

    snapshot = build_snapshot(
        booking,
        letter_date_val,
        signed_by=signed_by,
        signed_for=signed_for,
    )
    current_canon = build_canonical_snapshot_for_placement(booking, letter_date_val)
    current_hash = hash_canonical_snapshot(current_canon)

    # Placement Advice FINAL rule
    if baseline_letter is not None:
        base_snapshot = (baseline_letter.snapshot_json or {})
        base_canon = base_snapshot.get("canonical")
        base_hash = base_snapshot.get("content_hash")

        # Recompute for safety/consistency (hash ignores letter_date)
        if base_canon:
            base_hash = hash_canonical_snapshot(base_canon)

        if not base_canon or not base_hash:
            flash(
                "Baseline Placement Advice exists. Snapshot not stored for auto-change detection; serving issued letter.",
                "info",
            )
            return send_file(
                str(baseline_letter.pdf_path),
                as_attachment=True,
                download_name=clean_filename_keep_spaces(Path(baseline_letter.pdf_path).name),
                mimetype="application/pdf",
            )

        # No change => serve baseline
        if base_hash == current_hash:
            return send_file(
                str(baseline_letter.pdf_path),
                as_attachment=True,
                download_name=clean_filename_keep_spaces(Path(baseline_letter.pdf_path).name),
                mimetype="application/pdf",
            )

        # If an identical MOD for this current_hash already exists, just serve it.
        existing_mod = _find_existing_mod_for_hash(booking.id, current_hash)
        if existing_mod and existing_mod.pdf_path and Path(existing_mod.pdf_path).exists():
            return send_file(
                str(existing_mod.pdf_path),
                as_attachment=True,
                download_name=clean_filename_keep_spaces(f"MOD - {Path(existing_mod.pdf_path).name}"),
                mimetype="application/pdf",
            )

        # Changes -> issue Modification Advice
        letter_type_mod = "PLACEMENT_MOD"
        mod_seq = next_letter_sequence(booking.id, letter_type_mod)
        out_dir = booking_letters_dir(booking.id)

        mod_pdf = out_dir / f"placement_mod_v{mod_seq:03d}.pdf"

        ag = booking.agreement
        trip_serial = snapshot["trip_serial"]

        # Keep base letter no / date exactly as before
        base_letter_no = f"No.{(ag.placement_ref_prefix or '').strip().strip('/')}/Transport/Placement/{trip_serial}"
        base_letter_date = baseline_letter.letter_date or letter_date_val

        # Kept for compatibility (pdf_modification prints its own format anyway)
        mod_letter_no = f"No.{(ag.placement_ref_prefix or '').strip().strip('/')}/Transport/Placement/Mod/{trip_serial}/{mod_seq}"

        diffs = compute_mod_diff(base_canon, current_canon)

        generate_modification_advice_pdf(
            snapshot=snapshot,
            base_letter_no=base_letter_no,
            base_letter_date=base_letter_date,
            mod_letter_no=mod_letter_no,
            diffs=diffs,
            out_path=mod_pdf,
        )

        mod_letter = BookingLetter(
            booking_id=booking.id,
            letter_type=letter_type_mod,
            sequence_no=mod_seq,
            letter_date=letter_date_val,
            snapshot_json={
                "base_letter_id": baseline_letter.id,
                "base_letter_type": letter_type_base,
                "base_content_hash": base_hash,
                "content_hash": current_hash,
                "canonical": current_canon,
                "signatory": {
                    "signed_by_id": (signed_by.id if signed_by else None),
                    "signed_for_id": (signed_for.id if signed_for else None),
                    "signed_by_name": (signed_by.name if signed_by else None),
                    "signed_by_designation": (signed_by.designation if signed_by else None),
                    "signed_for_name": (signed_for.name if signed_for else None),
                    "signed_for_designation": (signed_for.designation if signed_for else None),
                },
                "diffs": [{"field": f, "old": o, "new": n} for (f, o, n) in diffs],
            },
            pdf_path=str(mod_pdf),
        )
        db.session.add(mod_letter)
        db.session.commit()

        return send_file(
            str(mod_pdf),
            as_attachment=True,
            download_name=clean_filename_keep_spaces(f"MOD - {Path(mod_pdf).name}"),
            mimetype="application/pdf",
        )

    # ---------------------------------------------------------------------
    # First baseline issue
    # ---------------------------------------------------------------------
    letter_type = "PLACEMENT"
    seq = next_letter_sequence(booking.id, letter_type)
    out_dir = booking_letters_dir(booking.id)

    base_pdf = out_dir / f"placement_advice_v{seq:03d}.pdf"
    merged_pdf = out_dir / f"placement_advice_v{seq:03d}_merged.pdf"

    generate_placement_advice_pdf(snapshot, base_pdf)

    if requires_attachment:
        f = request.files.get("attachment_pdf")
        assert f is not None
        original_name = f.filename
        safe_name = secure_filename(original_name)
        uploaded_path = out_dir / f"placement_attachment_v{seq:03d}_{safe_name}"
        f.save(str(uploaded_path))

        merge_pdfs(base_pdf, uploaded_path, merged_pdf)
        final_path = merged_pdf
    else:
        final_path = base_pdf

    letter = BookingLetter(
        booking_id=booking.id,
        letter_type=letter_type,
        sequence_no=seq,
        letter_date=letter_date_val,
        snapshot_json={
            "booking_id": booking.id,
            "trip_serial": snapshot["trip_serial"],
            "letter_date": snapshot["letter_date"].isoformat(),
            "content_hash": current_hash,
            "canonical": current_canon,
            "signatory": {
                "signed_by_id": (signed_by.id if signed_by else None),
                "signed_for_id": (signed_for.id if signed_for else None),
                "signed_by_name": (signed_by.name if signed_by else None),
                "signed_by_designation": (signed_by.designation if signed_by else None),
                "signed_for_name": (signed_for.name if signed_for else None),
                "signed_for_designation": (signed_for.designation if signed_for else None),
            },
        },
        pdf_path=str(final_path),
    )
    db.session.add(letter)
    db.session.flush()  # need letter.id before adding attachment row

    if uploaded_path and original_name:
        att = BookingLetterAttachment(
            booking_letter_id=letter.id,
            stored_path=str(uploaded_path),
            original_filename=original_name,
        )
        db.session.add(att)

    db.session.commit()

    return send_file(
        str(final_path),
        as_attachment=True,
        download_name=_download_name_for_placement(snapshot),
        mimetype="application/pdf",
    )
