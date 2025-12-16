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

    # -------------------------
    # Soft delete / status flags
    # -------------------------
    # ACTIVE  – normal booking
    # CANCELLED – soft-deleted, must remain in DB
    status = db.Column(db.String(20), nullable=False, default="ACTIVE", index=True)

    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))

    # convenience relationships
    agreement = db.relationship("Agreement")
    company = db.relationship("Company")
    lorry = db.relationship("LorryDetails")
    route = db.relationship("Route")

    # --- Materials: one booking → many material tables (typically one per loading point) ---
    material_tables = db.relationship(
        "BookingMaterial",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingMaterial.id",
    )

    @property
    def material_table(self):
        """
        Backwards-compatible alias for legacy code that still expects a single
        material table per booking. Returns the first material table if any,
        otherwise None.
        """
        return self.material_tables[0] if self.material_tables else None

    def __repr__(self):
        return f"<Booking id={self.id} route={self.route_id} km={self.trip_km}>"

    def cancel(self, reason: str | None = None):
        self.status = "CANCELLED"
        self.cancelled_at = datetime.utcnow()
        self.cancel_reason = (reason or "").strip() or None

    @property
    def is_cancelled(self) -> bool:
        return self.status == "CANCELLED"


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

    # materials where this BA is the FROM side
    materials_from = db.relationship(
        "BookingMaterial",
        foreign_keys="BookingMaterial.booking_authority_id",
        back_populates="booking_authority",
        lazy="select",
    )

    # materials where this BA is the TO side
    materials_to = db.relationship(
        "BookingMaterial",
        foreign_keys="BookingMaterial.to_booking_authority_id",
        back_populates="to_booking_authority",
        lazy="select",
    )

    @property
    def material_table(self):
        """
        Backwards-compatible convenience:
        for now we treat the *first* FROM-material as "the" table
        for this authority, if code ever wants ba.material_table.
        """
        return self.materials_from[0] if self.materials_from else None

    def __repr__(self):
        return (
            f"<BookingAuthority booking={self.booking_id} "
            f"authority={self.authority_id} role={self.role}>"
        )
class BookingMaterial(db.Model):
    __tablename__ = "booking_material"

    id = db.Column(db.Integer, primary_key=True)

    # Many material tables per booking (typically one per loading point)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("booking.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "FROM" side in this booking (usually a LOADING BookingAuthority)
    booking_authority_id = db.Column(
        db.Integer,
        db.ForeignKey("booking_authority.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional "TO" side (for destination authority)
    to_booking_authority_id = db.Column(
        db.Integer,
        db.ForeignKey("booking_authority.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Modes:
    #   "ITEM"     → item-wise detailed list
    #   "LUMPSUM"  → descriptive list + booking-level totals
    mode = db.Column(db.String(10), nullable=False, default="ITEM")

    # Header totals (only meaningful for LUMPSUM, automatically derived in ITEM)
    total_quantity = db.Column(db.Float)               # overall quantity if applicable
    total_quantity_unit = db.Column(db.String(50))     # "Ton", "MT", "Pkg", etc.
    total_amount = db.Column(db.Float)                 # total amount for this material table

    # Ordering of material tables within a booking (follow loading sequence)
    sequence_index = db.Column(db.Integer, nullable=False, default=1)

    # --- ORM relationships ---

    # Back to booking, as before
    booking = db.relationship(
        "Booking",
        back_populates="material_tables",
        lazy="joined",
    )

    # FROM side: the loading point this material belongs to
    booking_authority = db.relationship(
        "BookingAuthority",
        foreign_keys=[booking_authority_id],
        back_populates="materials_from",
        lazy="joined",
    )

    # TO side: optional destination point for this material
    to_booking_authority = db.relationship(
        "BookingAuthority",
        foreign_keys=[to_booking_authority_id],
        back_populates="materials_to",
        lazy="joined",
    )

    lines = db.relationship(
        "BookingMaterialLine",
        backref="material_table",
        cascade="all, delete-orphan",
        order_by="BookingMaterialLine.sequence_index",
        lazy="joined",
    )

    def __repr__(self):
        return (
            f"<BookingMaterial id={self.id} booking={self.booking_id} "
            f"ba={self.booking_authority_id} to_ba={self.to_booking_authority_id} "
            f"mode={self.mode}>"
        )


class BookingMaterialLine(db.Model):
    __tablename__ = "booking_material_line"

    id = db.Column(db.Integer, primary_key=True)

    booking_material_id = db.Column(
        db.Integer,
        db.ForeignKey("booking_material.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Sl.No / ordering
    sequence_index = db.Column(db.Integer, nullable=False, default=1)

    # Always required
    description = db.Column(db.String(250), nullable=False)

    # Optional: quantity details
    unit = db.Column(db.String(50))        # e.g., "Ton", "Pkg"
    quantity = db.Column(db.Float)         # optional, per-line

    # Item-wise only
    rate = db.Column(db.Float)             # optional
    amount = db.Column(db.Float)           # optional (qty * rate for ITEM)

    def __repr__(self):
        return (
            f"<BookingMaterialLine tbl={self.booking_material_id} sl={self.sequence_index} "
            f"desc='{self.description}'>"
        )
