from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app import db
from models import Booking, User
from forms import BookingForm, RescheduleRequestForm

bookings_bp = Blueprint("bookings", __name__)


# ---------------------------------------------------------------------------
# LIST — shows who accepted each booking
# ---------------------------------------------------------------------------
@bookings_bp.route("/")
@login_required
def list_bookings():
    bookings = Booking.query.order_by(Booking.scheduled_at.desc()).all()
    return render_template("bookings/list.html", bookings=bookings)


# ---------------------------------------------------------------------------
# DETAIL
# ---------------------------------------------------------------------------
@bookings_bp.route("/<int:booking_id>")
@login_required
def detail(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        abort(404)
    return render_template("bookings/detail.html", booking=booking)


# ---------------------------------------------------------------------------
# ACCEPT — records WHO accepted
# ---------------------------------------------------------------------------
@bookings_bp.route("/<int:booking_id>/accept", methods=["POST"])
@login_required
def accept(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "pending":
        flash("Booking cannot be accepted.", "danger")
        return redirect(url_for("bookings.list_bookings"))

    booking.status = "accepted"
    booking.accepted_by_id = current_user.id
    booking.accepted_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f"Booking #{booking.id} accepted by {current_user.username}.", "success")
    return redirect(url_for("bookings.list_bookings"))


# ---------------------------------------------------------------------------
# DECLINE
# ---------------------------------------------------------------------------
@bookings_bp.route("/<int:booking_id>/decline", methods=["POST"])
@login_required
def decline(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "pending":
        flash("Booking cannot be declined.", "danger")
        return redirect(url_for("bookings.list_bookings"))
    booking.status = "declined"
    db.session.commit()
    flash(f"Booking #{booking.id} declined.", "info")
    return redirect(url_for("bookings.list_bookings"))


# ---------------------------------------------------------------------------
# RESCHEDULE — customer-facing, within 3-day window after acceptance
# ---------------------------------------------------------------------------
@bookings_bp.route("/<int:booking_id>/reschedule", methods=["GET", "POST"])
@login_required
def reschedule(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        abort(404)

    # Guard: must be accepted and within the 3-day window.
    if not booking.can_customer_reschedule:
        if booking.status == "accepted":
            flash("Reschedule window has closed (3 days after acceptance).", "danger")
        else:
            flash("Only accepted bookings can be rescheduled.", "danger")
        return redirect(url_for("bookings.detail", booking_id=booking.id))

    form = RescheduleRequestForm()
    if form.validate_on_submit():
        booking.status = "reschedule_requested"
        booking.reschedule_new_time = form.new_time.data
        booking.reschedule_reason = form.reason.data
        booking.reschedule_requested_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Reschedule request submitted for approval.", "success")
        return redirect(url_for("bookings.detail", booking_id=booking.id))

    return render_template("bookings/reschedule.html", booking=booking, form=form)


# ---------------------------------------------------------------------------
# APPROVE / DECLINE RESCHEDULE — caretaker or admin action
# ---------------------------------------------------------------------------
@bookings_bp.route("/<int:booking_id>/reschedule/approve", methods=["POST"])
@login_required
def approve_reschedule(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "reschedule_requested":
        flash("No reschedule request to approve.", "danger")
        return redirect(url_for("bookings.list_bookings"))

    booking.scheduled_at = booking.reschedule_new_time
    booking.status = "accepted"
    booking.accepted_by_id = current_user.id
    booking.accepted_at = datetime.now(timezone.utc)
    booking.reschedule_new_time = None
    booking.reschedule_requested_at = None
    booking.reschedule_reason = None
    db.session.commit()
    flash(f"Reschedule approved by {current_user.username}.  New 3-day window starts now.", "success")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


@bookings_bp.route("/<int:booking_id>/reschedule/decline", methods=["POST"])
@login_required
def decline_reschedule(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "reschedule_requested":
        flash("No reschedule request to decline.", "danger")
        return redirect(url_for("bookings.list_bookings"))

    booking.status = "accepted"
    booking.reschedule_new_time = None
    booking.reschedule_requested_at = None
    booking.reschedule_reason = None
    db.session.commit()
    flash("Reschedule request declined.  Original time stands.", "info")
    return redirect(url_for("bookings.detail", booking_id=booking.id))


# ---------------------------------------------------------------------------
# COMPLETE / CANCEL
# ---------------------------------------------------------------------------
@bookings_bp.route("/<int:booking_id>/complete", methods=["POST"])
@login_required
def complete(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "accepted":
        flash("Only accepted bookings can be marked complete.", "danger")
        return redirect(url_for("bookings.list_bookings"))
    booking.status = "completed"
    db.session.commit()
    flash("Booking marked as completed.", "success")
    return redirect(url_for("bookings.list_bookings"))


@bookings_bp.route("/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        abort(404)
    booking.status = "cancelled"
    db.session.commit()
    flash("Booking cancelled.", "info")
    return redirect(url_for("bookings.list_bookings"))
