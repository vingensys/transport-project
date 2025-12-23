from flask import render_template, request, redirect, url_for, flash

from . import admin_bp
from transport.models import (
    db,
    Location,
    Authority,
    AppConfig,
    LetterSignatory,
)

from .dashboard_common import (
    get_core_master_data,
    get_authorities_and_locations,
    get_latest_app_config,
)
from .dashboard_locations import get_locations_pagination_context
from .dashboard_booking import get_booking_history_context
from .dashboard_overview import get_overview_context


@admin_bp.route("/")
def dashboard():
    # Default landing: Overview tab (use query param; hash is not sent to server)
    tab = (request.args.get("tab") or "").strip().lower()
    if not tab:
        args = request.args.to_dict(flat=True)
        args["tab"] = "overview"
        return redirect(url_for("admin.dashboard", **args))

    ctx = {}

    # Core master data for tabs
    ctx.update(get_core_master_data())

    # Authorities + locations + booking_auth_map
    ctx.update(get_authorities_and_locations())

    # Locations tab pagination
    ctx.update(get_locations_pagination_context())

    # Home depot config (latest row, consistent)
    ctx.update(get_latest_app_config())

    # Booking/history context (uses agreements + home_location_id)
    booking_ctx = get_booking_history_context(
        agreements=ctx["agreements"],
        home_location_id=ctx.get("home_location_id"),
    )
    ctx.update(booking_ctx)

    # Overview tab context (depends on active_agreement)
    ctx.update(get_overview_context(ctx.get("active_agreement")))

    return render_template(
        "admin/dashboard.html",
        **ctx,
    )


@admin_bp.route("/app-config/save", methods=["POST"])
def save_app_config():
    """
    Create or update AppConfig.
    Refactor decision: use latest row consistently.
    """
    raw_loc = (request.form.get("home_location_input") or "").strip()
    raw_auth = (request.form.get("home_authority_id") or "").strip()

    if not raw_loc:
        flash("Home depot location is required.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    code = None
    if "[" in raw_loc and "]" in raw_loc:
        start = raw_loc.rfind("[")
        end = raw_loc.rfind("]")
        if start != -1 and end != -1 and end > start + 1:
            code = raw_loc[start + 1 : end].strip().upper()

    if not code:
        parts = raw_loc.split()
        if parts:
            code = parts[-1].strip("[]").upper()

    if not code:
        flash("Could not determine station code from home depot input.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    home_location = Location.query.filter_by(code=code).first()
    if not home_location:
        flash(f"Unknown location code for home depot: {code}", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    # Home authority is optional
    home_authority = None
    if raw_auth:
        try:
            auth_id = int(raw_auth)
            home_authority = Authority.query.get(auth_id)
            if not home_authority:
                flash("Selected home authority does not exist.", "error")
                return redirect(url_for("admin.dashboard") + "#config")
        except ValueError:
            flash("Invalid home authority selection.", "error")
            return redirect(url_for("admin.dashboard") + "#config")

    app_config = AppConfig.query.order_by(AppConfig.id.desc()).first()
    if not app_config:
        app_config = AppConfig()
        db.session.add(app_config)

    app_config.home_location_id = home_location.id
    app_config.home_authority_id = home_authority.id if home_authority else None

    db.session.commit()
    flash(
        f"Home depot set to {home_location.name} [{home_location.code}].",
        "success",
    )
    return redirect(url_for("admin.dashboard") + "#config")


# =============================================================================
# Letter Signatory (master data)
# =============================================================================

def _to_int(val, default: int) -> int:
    try:
        return int(val)
    except Exception:
        return default


@admin_bp.route("/config/letter-signatory/create", methods=["POST"])
def create_letter_signatory():
    name = (request.form.get("name") or "").strip()
    designation = (request.form.get("designation") or "").strip()

    if not name:
        flash("Signatory name is required.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    if not designation:
        flash("Signatory designation is required.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    sort_order = _to_int(request.form.get("sort_order"), 1)

    # checkbox semantics: if present => truthy
    is_active = bool(request.form.get("is_active") or request.form.get("active"))

    # If UI doesn't send any checkbox at all, default active = True
    if "is_active" not in request.form and "active" not in request.form:
        is_active = True

    s = LetterSignatory(
        name=name,
        designation=designation,
        sort_order=sort_order,
        is_active=is_active,
    )
    db.session.add(s)
    db.session.commit()
    flash("Letter signatory added.", "success")
    return redirect(url_for("admin.dashboard") + "#config")


@admin_bp.route("/config/letter-signatory/<int:signatory_id>/toggle", methods=["POST"])
def toggle_letter_signatory(signatory_id: int):
    s = LetterSignatory.query.get_or_404(signatory_id)
    s.is_active = not bool(s.is_active)
    db.session.commit()
    flash(
        f"Signatory {'enabled' if s.is_active else 'disabled'}.",
        "success",
    )
    return redirect(url_for("admin.dashboard") + "#config")


@admin_bp.route("/config/letter-signatory/<int:signatory_id>/update", methods=["POST"])
def update_letter_signatory(signatory_id: int):
    s = LetterSignatory.query.get_or_404(signatory_id)

    name = (request.form.get("name") or "").strip()
    designation = (request.form.get("designation") or "").strip()

    if not name:
        flash("Signatory name is required.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    if not designation:
        flash("Signatory designation is required.", "error")
        return redirect(url_for("admin.dashboard") + "#config")

    s.name = name
    s.designation = designation
    s.sort_order = _to_int(request.form.get("sort_order"), s.sort_order or 1)

    # If checkbox is present => set true, else set false.
    # (This is standard HTML checkbox behavior when the checkbox exists in form.)
    if "is_active" in request.form or "active" in request.form:
        s.is_active = bool(request.form.get("is_active") or request.form.get("active"))
    else:
        # If no checkbox fields, leave as-is (supports forms that only edit text)
        pass

    db.session.commit()
    flash("Signatory updated.", "success")
    return redirect(url_for("admin.dashboard") + "#config")
