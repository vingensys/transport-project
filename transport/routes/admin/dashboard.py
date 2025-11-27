from flask import render_template, request
from . import admin_bp
from transport.models import Company, Agreement, LorryDetails, Location, Authority, Route   # 👈 add models here


@admin_bp.route("/")
def dashboard():
    companies = Company.query.order_by(Company.id.desc()).all()
    agreements = Agreement.query.order_by(Agreement.id.desc()).all()  # 👈 new
    lorries = LorryDetails.query.order_by(LorryDetails.id.desc()).all()
    
    # Pagination for Locations
    loc_page = request.args.get("loc_page", 1, type=int)
    LOC_PAGE_SIZE = 50

    locations_query = Location.query.order_by(Location.code)
    locations = locations_query.paginate(page=loc_page, per_page=LOC_PAGE_SIZE, error_out=False)

    # Pagination window setup
    total_pages = locations.pages
    current_page = locations.page
    window = 4  # how many pages to show on each side of current

    start_page = max(1, current_page - window)
    end_page = min(total_pages, current_page + window)

    # Authorities + full location list for the datalist in Authorities tab
    authorities = Authority.query.order_by(Authority.id.desc()).all()
    all_locations = Location.query.order_by(Location.code).all()

    # All routes (for Route Builder tab)
    routes = Route.query.order_by(Route.id.desc()).all()

    return render_template(
        "admin/dashboard.html",
        companies=companies,
        agreements=agreements,
        lorries=lorries,
        locations=locations,

        loc_page=current_page,
        loc_total_pages=total_pages,
        loc_start_page=start_page,
        loc_end_page=end_page,

        authorities=authorities,
        all_locations=all_locations,

        routes=routes,
    )

