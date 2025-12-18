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

    # Letter-only reference prefix
    # Example: "SA/A/RS/ED/OT"
    placement_ref_prefix = db.Column(db.String(150), nullable=True)

    total_mt_km = db.Column(db.Float, nullable=False)
    rate_per_mt_km = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=False)

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
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))

    def __repr__(self):
        return f"<Location {self.code} - {self.name}>"


class Authority(db.Model):
    __tablename__ = "authority"

    id = db.Column(db.Integer, primary_key=True)

    location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)
    location = db.relationship("Location", backref="authorities")

    authority_title = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))

    def __repr__(self):
        return f"<Authority {self.authority_title} @ {self.location.code}>"


class Route(db.Model):
    __tablename__ = "route"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    total_km = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    remarks = db.Column(db.String(250))

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

    sequence_index = db.Column(db.Integer, nullable=False)
    is_start_cluster = db.Column(db.Boolean, nullable=False, default=False)
    is_end_cluster = db.Column(db.Boolean, nullable=False, default=False)
    remarks = db.Column(db.String(200))

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
    route_id = db.Column(db.Integer, db.ForeignKey("route.id"), nullable=False)

    trip_km = db.Column(db.Integer, nullable=False)
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

    status = db.Column(db.String(20), nullable=False, default="ACTIVE", index=True)
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))

    agreement = db.relationship("Agreement")
    company = db.relationship("Company")
    lorry = db.relationship("LorryDetails")
    route = db.relationship("Route")

    material_tables = db.relationship(
        "BookingMaterial",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingMaterial.id",
    )

    @property
    def material_table(self):
        return self.material_tables[0] if self.material_tables else None

    def cancel(self, reason: str | None = None):
        self.status = "CANCELLED"
        self.cancelled_at = datetime.utcnow()
        self.cancel_reason = (reason or "").strip() or None

    @property
    def is_cancelled(self) -> bool:
        return self.status == "CANCELLED"

    def __repr__(self):
        return f"<Booking id={self.id} route={self.route_id} km={self.trip_km}>"


class BookingAuthority(db.Model):
    __tablename__ = "booking_authority"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    authority_id = db.Column(db.Integer, db.ForeignKey("authority.id"), nullable=False)

    role = db.Column(db.String(20), nullable=False)
    sequence_index = db.Column(db.Integer, nullable=False, default=1)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    booking = db.relationship("Booking", backref="booking_authorities")
    authority = db.relationship("Authority")

    materials_from = db.relationship(
        "BookingMaterial",
        foreign_keys="BookingMaterial.booking_authority_id",
        back_populates="booking_authority",
        lazy="select",
    )

    materials_to = db.relationship(
        "BookingMaterial",
        foreign_keys="BookingMaterial.to_booking_authority_id",
        back_populates="to_booking_authority",
        lazy="select",
    )

    @property
    def material_table(self):
        return self.materials_from[0] if self.materials_from else None

    def __repr__(self):
        return (
            f"<BookingAuthority booking={self.booking_id} "
            f"authority={self.authority_id} role={self.role}>"
        )


class BookingMaterial(db.Model):
    __tablename__ = "booking_material"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("booking.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    booking_authority_id = db.Column(
        db.Integer,
        db.ForeignKey("booking_authority.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    to_booking_authority_id = db.Column(
        db.Integer,
        db.ForeignKey("booking_authority.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    mode = db.Column(db.String(10), nullable=False, default="ITEM")

    total_quantity = db.Column(db.Float)
    total_quantity_unit = db.Column(db.String(50))
    total_amount = db.Column(db.Float)

    sequence_index = db.Column(db.Integer, nullable=False, default=1)

    booking = db.relationship(
        "Booking",
        back_populates="material_tables",
        lazy="joined",
    )

    booking_authority = db.relationship(
        "BookingAuthority",
        foreign_keys=[booking_authority_id],
        back_populates="materials_from",
        lazy="joined",
    )

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

    sequence_index = db.Column(db.Integer, nullable=False, default=1)
    description = db.Column(db.String(250), nullable=False)

    unit = db.Column(db.String(50))
    quantity = db.Column(db.Float)
    rate = db.Column(db.Float)
    amount = db.Column(db.Float)

    def __repr__(self):
        return (
            f"<BookingMaterialLine tbl={self.booking_material_id} sl={self.sequence_index} "
            f"desc='{self.description}'>"
        )


# -------------------------------------------------------------------
# LETTER MODULE (new, isolated, no impact on booking/material logic)
# -------------------------------------------------------------------

class BookingLetter(db.Model):
    __tablename__ = "booking_letter"

    id = db.Column(db.Integer, primary_key=True)

    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)

    # PLACEMENT / MODIFICATION / CANCELLATION / AUTHORIZATION
    letter_type = db.Column(db.String(20), nullable=False)

    # Sequence per booking + letter_type
    sequence_no = db.Column(db.Integer, nullable=False)

    letter_date = db.Column(db.Date, nullable=False)

    # Frozen context used to generate this letter
    snapshot_json = db.Column(db.JSON, nullable=False)

    # Final merged PDF path
    pdf_path = db.Column(db.String(300), nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    booking = db.relationship("Booking")

    def __repr__(self):
        return f"<BookingLetter {self.letter_type} booking={self.booking_id} seq={self.sequence_no}>"


class BookingLetterAttachment(db.Model):
    __tablename__ = "booking_letter_attachment"

    id = db.Column(db.Integer, primary_key=True)

    booking_letter_id = db.Column(
        db.Integer, db.ForeignKey("booking_letter.id"), nullable=False
    )

    stored_path = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)

    letter = db.relationship("BookingLetter", backref="attachments")

    def __repr__(self):
        return f"<BookingLetterAttachment letter={self.booking_letter_id}>"
