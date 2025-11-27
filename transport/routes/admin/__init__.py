from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Import routes so they register on blueprint
from . import dashboard, companies, agreements, lorries, locations, authorities, routes