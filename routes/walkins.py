from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app import db
from models import Booking, WalkInPaymentProof
from forms import WalkInForm

walkins_bp = Blueprint("walkins", __name__, url_prefix="/walkins")


# ---------------------------------------------------------------------------
# CREATE WALK-IN — caretakers only, records payment proof
# ---------------------------------------------------------------------------
@walkins_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = WalkInForm()
    if form.validate_on_submit():
        # 1. Create the booking
        booking = Booking(
            customer_name=form.customer_name.data,
            customer_contact=form.customer_contact.data,
            service=form.service.data,
            scheduled_at=form.scheduled_at.data,
            status="accepted",
            is_walkin=True,
            created_by_id=current_user.id,
            accepted_by_id=current_user.id,
            accepted_at=datetime.now(timezone.utc),
        )
        db.session.add(booking)
        db.session.flush()  # get booking.id

        # 2. Attach payment proof (handled outside, recorded here)
        proof = WalkInPaymentProof(
            booking_id=booking.id,
            payer_name=form.payer_name.data,
            payer_signature=form.payer_signature.data,
            amount=form.amount.data,
            recorded_by_id=current_user.id,
        )
        db.session.add(proof)
        db.session.commit()

        flash(
            f"Walk-in #{booking.id} recorded for {booking.customer_name}.  "
            f"Payment proof captured under {proof.payer_name}.",
            "success",
        )
        return redirect(url_for("walkins.list_walkins"))

    return render_template("walkins/create.html", form=form)


# ---------------------------------------------------------------------------
# LIST WALK-INS
# ---------------------------------------------------------------------------
@walkins_bp.route("/")
@login_required
def list_walkins():
    walkins = (
        Booking.query
        .filter_by(is_walkin=True)
        .order_by(Booking.scheduled_at.desc())
        .all()
    )
    return render_template("walkins/list.html", walkins=walkins)


# ---------------------------------------------------------------------------
# DETAIL — includes payment proof
# ---------------------------------------------------------------------------
@walkins_bp.route("/<int:booking_id>")
@login_required
def detail(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or not booking.is_walkin:
        abort(404)
    proof = WalkInPaymentProof.query.filter_by(booking_id=booking.id).first()
    return render_template("walkins/detail.html", booking=booking, proof=proof)
