from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()

class Company(db.Model):
    __tablename__ = "company"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))

    def __repr__(self) -> str:
        return f"<Company {self.id} {self.name}>"

class Agreement(db.Model):
    __tablename__ = "agreement"

    id = db.Column(db.Integer, primary_key=True)
    loa_number = db.Column(db.String(100), nullable=False)
    total_mt_km = db.Column(db.Float, nullable=False)
    rate_per_mt_km = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=False)

    # Relationship to company
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
    company = db.relationship("Company", backref="agreements")

    def __repr__(self):
        return f"<Agreement {self.id} LOA={self.loa_number}>"

class LorryDetails(db.Model):
    __tablename__ = "lorry_details"

    id = db.Column(db.Integer, primary_key=True)
    capacity = db.Column(db.Integer, nullable=False)
    carrier_size = db.Column(db.String(50), nullable=False)
    number_of_wheels = db.Column(db.Integer, nullable=False)
    remarks = db.Column(db.String(200))

    def __repr__(self):
        return f"<Lorry {self.id} {self.capacity}>"

class Location(db.Model):
    __tablename__ = "location"

    id = db.Column(db.Integer, primary_key=True)

    # Short code like NDLS, ED, MAS, TVC
    code = db.Column(db.String(10), unique=True, nullable=False)

    # Full name like "New Delhi", "Erode Junction"
    name = db.Column(db.String(100), nullable=False)

    # Optional address or description
    address = db.Column(db.String(200))

    def __repr__(self):
        return f"<Location {self.code} - {self.name}>"

class Authority(db.Model):
    __tablename__ = "authority"

    id = db.Column(db.Integer, primary_key=True)

    # FK → Location
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)
    location = db.relationship("Location", backref="authorities")

    # Designation (e.g., "Station Master", "CGS", "Yard Supervisor")
    authority_title = db.Column(db.String(100), nullable=False)

    # Optional office address
    address = db.Column(db.String(200))

    def __repr__(self):
        return f"<Authority {self.authority_title} @ {self.location.code}>"

class Route(db.Model):
    __tablename__ = "route"

    id = db.Column(db.Integer, primary_key=True)

    # Short code / reference for the route (e.g., "RPM_PER_AJJ_ED_R1")
    code = db.Column(db.String(50), unique=True, nullable=False)

    # Human-readable name (e.g., "RPM – PER – AJJ – ED (via PER cluster)")
    name = db.Column(db.String(200), nullable=False)

    # Total length of the route in kilometers
    total_km = db.Column(db.Integer, nullable=False)

    # Active/inactive for operational use
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Optional remarks
    remarks = db.Column(db.String(250))

    # Relationship to RouteStop (ordered by sequence_index)
    stops = db.relationship(
        "RouteStop",
        backref="route",
        cascade="all, delete-orphan",
        order_by="RouteStop.sequence_index",
    )

    def __repr__(self):
        return f"<Route {self.code} ({self.total_km} km)>"


class RouteStop(db.Model):
    __tablename__ = "route_stop"

    id = db.Column(db.Integer, primary_key=True)

    route_id = db.Column(db.Integer, db.ForeignKey("route.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)

    # Order along the route: 1, 2, 3, ...
    sequence_index = db.Column(db.Integer, nullable=False)

    # Mark if this stop belongs to the start cluster and/or end cluster
    is_start_cluster = db.Column(db.Boolean, nullable=False, default=False)
    is_end_cluster = db.Column(db.Boolean, nullable=False, default=False)

    # Optional remarks for this stop (e.g., "Yard", "Goods Shed")
    remarks = db.Column(db.String(200))

    # Convenience relationship to Location
    location = db.relationship("Location")

    def __repr__(self):
        return (
            f"<RouteStop route={self.route_id} seq={self.sequence_index} "
            f"loc={self.location_id} start={self.is_start_cluster} end={self.is_end_cluster}>"
        )

class AppConfig(db.Model):
    __tablename__ = "app_config"

    id = db.Column(db.Integer, primary_key=True)

    home_location_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    home_authority_id = db.Column(db.Integer, db.ForeignKey("authority.id"))

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    home_location = db.relationship("Location", foreign_keys=[home_location_id])
    home_authority = db.relationship("Authority", foreign_keys=[home_authority_id])

    def __repr__(self):
        return f"<AppConfig home_location={self.home_location_id} home_authority={self.home_authority_id}>"

class Booking(db.Model):
    __tablename__ = "booking"

    id = db.Column(db.Integer, primary_key=True)

    agreement_id = db.Column(db.Integer, db.ForeignKey("agreement.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("company.id"), nullable=False)
    lorry_id = db.Column(db.Integer, db.ForeignKey("lorry_details.id"), nullable=False)

    # Route ALWAYS present (matched/created from sequence)
    route_id = db.Column(db.Integer, db.ForeignKey("route.id"), nullable=False)

    # Either from the route (if matched) or supplied by user
    trip_km = db.Column(db.Integer, nullable=False)

    # When the lorry is actually required / placed
    placement_date = db.Column(db.Date, nullable=False, default=date.today)

    booking_date = db.Column(db.Date, nullable=False, default=date.today)

    remarks = db.Column(db.String(250))

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # convenience relationships
    agreement = db.relationship("Agreement")
    company = db.relationship("Company")
    lorry = db.relationship("LorryDetails")
    route = db.relationship("Route")

    def __repr__(self):
        return f"<Booking id={self.id} route={self.route_id} km={self.trip_km}>"

class BookingAuthority(db.Model):
    __tablename__ = "booking_authority"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    authority_id = db.Column(db.Integer, db.ForeignKey("authority.id"), nullable=False)

    # 'LOADING' or 'UNLOADING'
    role = db.Column(db.String(20), nullable=False)

    # ordering for letters (1,2,3...)
    sequence_index = db.Column(db.Integer, nullable=False, default=1)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    booking = db.relationship("Booking", backref="booking_authorities")
    authority = db.relationship("Authority")

    def __repr__(self):
        return f"<BookingAuthority booking={self.booking_id} authority={self.authority_id} role={self.role}>"
