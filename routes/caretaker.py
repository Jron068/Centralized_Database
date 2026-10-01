import os
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import redirect, flash, session, url_for, render_template
from flask import request, jsonify
from werkzeug.security import generate_password_hash

from templates.admin.app import app, mail
from config import get_connection
from flask_mail import Message
from models.decorators import role_required

def caretaker_page(template_name):
    if session.get("role") != "caretaker":
        return redirect(url_for("login"))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name, r.address, r.status
            FROM resorts r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (session.get("account_id"),),
        )
        resort = cursor.fetchone()
        if not resort:
            return redirect(url_for("login"))
        return render_template(
            template_name,
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker/updates")
@role_required("caretaker")
def caretaker_updates():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.resort_name
            FROM resorts r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (session.get("account_id"),),
        )
        resort = cursor.fetchone()
        if not resort:
            return redirect(url_for("login"))

        cursor.execute(
            """
            SELECT title, message, type, created_at
            FROM notifications
            WHERE account_id = %s
            ORDER BY created_at DESC
            """,
            (session.get("account_id"),),
        )
        updates = cursor.fetchall()
        return render_template(
            "caretaker/caretaker_updates.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            updates=updates,
        )
    finally:
        cursor.close()
        conn.close()

def _as_date(value):
    if isinstance(value, str):
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    return value.date() if isinstance(value, datetime) else value


def _stay_status(row, today):
    """Turn the reservation/payment status + dates into what the caretaker sees."""
    status = row["reservation_status"]
    if status == "Pending":
        return "Pending Verification"
    if status in {"Rejected", "Cancelled"}:
        return status
    if status == "Completed":
        return "Checked Out"
    if status == "Confirmed":
        check_in, check_out = _as_date(row["check_in"]), _as_date(row["check_out"])
        if today < check_in:
            return "Reserved"
        if check_in <= today < check_out or (check_in == check_out == today):
            return "Checked In"
        return "Checked Out"
    return status or "Reserved"


# Your reservations table needs a customer on every booking, so guests who have no account of their own
# are attached to ONE shared "walk-in guest" customer account (their real name is still saved on the booking).
# Register that account once through your normal customer sign-up using this email:
WALKIN_PLACEHOLDER_EMAIL = "walkin.guest@pansolresorts.com"

_COLUMN_CACHE = {}


def _table_columns(cursor, table):
    """Read-only look at a table's columns (information_schema). Nothing is ever altered."""
    if table not in _COLUMN_CACHE:
        cursor.execute(
            """
            SELECT COLUMN_NAME AS name, IS_NULLABLE AS nullable, COLUMN_DEFAULT AS dflt, EXTRA AS extra,
                   CHARACTER_MAXIMUM_LENGTH AS maxlen
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table,),
        )
        _COLUMN_CACHE[table] = {r["name"]: r for r in cursor.fetchall()}
    return _COLUMN_CACHE[table]


def _missing_required(columns, provided):
    """Columns that must have a value (NOT NULL, no default) but that we are not filling."""
    out = []
    for name, c in columns.items():
        extra = (c["extra"] or "").lower()
        if (
            c["nullable"] == "NO"
            and c["dflt"] is None
            and "auto_increment" not in extra
            and "generated" not in extra
            and name not in provided
        ):
            out.append(name)
    return out


def _walkin_schema(cursor):
    """Work out what the existing tables can store, so the walk-in feature needs no schema changes."""
    res = _table_columns(cursor, "reservations")
    pay = _table_columns(cursor, "payments")
    proof_table = "payments" if "proof_of_payment" in pay else ("reservations" if "proof_of_payment" in res else None)
    proof_expr = {"payments": "p.proof_of_payment", "reservations": "r.proof_of_payment"}.get(proof_table, "NULL")
    if "booking_source" in res:
        walkin_expr = "r.booking_source = 'Walk-in'"
    else:
        # No source column: walk-in photos are saved under static/uploads/walkin_proofs/, which identifies them
        walkin_expr = f"LOCATE('walkin_proofs/', COALESCE({proof_expr}, '')) > 0"
    account_optional = res.get("customer_id", {}).get("nullable") == "YES"
    placeholder = None
    if not account_optional:
        cursor.execute(
            """
            SELECT cu.customer_id, a.account_id
            FROM customers cu
            JOIN accounts a ON a.account_id = cu.account_id
            WHERE a.email = %s
            LIMIT 1
            """,
            (WALKIN_PLACEHOLDER_EMAIL,),
        )
        placeholder = cursor.fetchone()
    return {
        "placeholder": placeholder,
        "name_only": True,  # guests without an account can always be booked by name
        "res": res,
        "pay": pay,
        "proof_table": proof_table,
        "proof_expr": proof_expr,
        "walkin_expr": walkin_expr,
        "contact": "guest_contact" in res,
        "handled_by": "handled_by" in res,
        "total": "total_amount" in res,
        "account_optional": account_optional,
    }


def _guest_overview(cursor, account_id):
    """Rows + stat-card numbers for the caretaker Guests page (walk-in and online)."""
    schema = _walkin_schema(cursor)
    contact_expr = "r.guest_contact" if schema["contact"] else "NULL"
    cursor.execute(
        f"""
        SELECT r.reservation_id, r.guest_name, {contact_expr} AS guest_contact,
               r.check_in, r.check_out, r.guests, r.reservation_status,
               CASE WHEN {schema['walkin_expr']} THEN 'Walk-in' ELSE 'Online' END AS booking_source,
               p.amount_paid, p.payment_status, {schema['proof_expr']} AS proof_of_payment
        FROM reservations r
        JOIN caretakers c ON c.resort_id = r.resort_id
        LEFT JOIN payments p ON p.payment_id = (
            SELECT p2.payment_id FROM payments p2
            WHERE p2.reservation_id = r.reservation_id
            ORDER BY p2.payment_id DESC LIMIT 1
        )
        WHERE c.account_id = %s AND c.status = 'Active'
        ORDER BY r.created_at DESC, r.check_in DESC
        """,
        (account_id,),
    )
    today = date.today()
    guests = []
    stats = {"today_guests": 0, "checked_in": 0, "checked_out": 0, "upcoming": 0, "pending": 0}
    for r in cursor.fetchall():
        status = _stay_status(r, today)
        if status == "Checked In":
            stats["checked_in"] += 1
            stats["today_guests"] += r["guests"] or 0
        elif status == "Checked Out" and _as_date(r["check_out"]) == today:
            stats["checked_out"] += 1
        elif status == "Reserved":
            stats["upcoming"] += 1
        elif status == "Pending Verification":
            stats["pending"] += 1
        guests.append(
            {
                "id": r["reservation_id"],
                "booking": f"#RSV-{r['reservation_id']}",
                "guest": r["guest_name"] or "Guest",
                "contact": r["guest_contact"] or "",
                "check_in": str(r["check_in"]),
                "check_out": str(r["check_out"]),
                "guests": r["guests"],
                "source": r["booking_source"] or "Online",
                "amount": float(r["amount_paid"]) if r["amount_paid"] is not None else None,
                "proof": url_for("static", filename=r["proof_of_payment"]) if r["proof_of_payment"] else None,
                "status": status,
            }
        )
    return {"stats": stats, "guests": guests}


@app.route("/caretaker/guests")
@role_required("caretaker")
def caretaker_guests():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _walkin_resort(cursor)
        if not resort:
            return redirect(url_for("login"))
        schema = _walkin_schema(cursor)
        return render_template(
            "caretaker/caretaker_guests.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            data=_guest_overview(cursor, session.get("account_id")),
            features={
                "contact": True,
                "name_only": schema["name_only"],
                "placeholder_missing": not schema["name_only"],
                "placeholder_email": WALKIN_PLACEHOLDER_EMAIL,
            },
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/caretaker/guests/data")
@role_required("caretaker")
def caretaker_guests_data():
    """JSON feed the Guests page polls, so admin decisions show up without a reload."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        return jsonify(_guest_overview(cursor, session.get("account_id")))
    finally:
        cursor.close()
        conn.close()

def _customer_visible_clause(schema):
    """SQL that is true only for CUSTOMER reservations. Walk-ins are admin-only."""
    return f"NOT COALESCE(({schema['walkin_expr']}), 0)"


def _owner_account_id(cursor, owner_id):
    """resorts.owner_id points to owners.owner_id; notifications are addressed to the owner's account_id."""
    if not owner_id:
        return None
    cursor.execute("SELECT account_id FROM owners WHERE owner_id = %s", (owner_id,))
    row = cursor.fetchone()
    return row["account_id"] if row else None


def _dates_conflict(cursor, resort_id, check_in, check_out, exclude_id=None):
    """Return a CONFIRMED reservation that already occupies any of these dates at this resort (or None).
    Once the admin/caretaker approves a booking, its dates are occupied and nobody else can book them.
    Call this from every place that creates or approves a booking (customer booking route too)."""
    ci, co = _as_date(check_in), _as_date(check_out)
    if co <= ci:
        co = ci + timedelta(days=1)
    sql = (
        "SELECT reservation_id, check_in, check_out FROM reservations "
        "WHERE resort_id = %s AND reservation_status = 'Confirmed' "
        "AND check_in < %s AND GREATEST(check_out, DATE_ADD(check_in, INTERVAL 1 DAY)) > %s"
    )
    params = [resort_id, co, ci]
    if exclude_id:
        sql += " AND reservation_id <> %s"
        params.append(exclude_id)
    cursor.execute(sql + " LIMIT 1", tuple(params))
    return cursor.fetchone()


def _clash_text(clash):
    return f"already occupied by confirmed booking #RSV-{clash['reservation_id']} ({clash['check_in']} to {clash['check_out']})"


def occupied_dates(cursor, resort_id):
    """List of 'YYYY-MM-DD' strings occupied by CONFIRMED bookings at this resort (for the customer calendar).
    Use it in /resort_availability:  return jsonify({"booked_dates": occupied_dates(cursor, resort_id)})"""
    cursor.execute(
        "SELECT check_in, check_out FROM reservations "
        "WHERE resort_id = %s AND reservation_status = 'Confirmed' AND check_out >= CURDATE()",
        (resort_id,),
    )
    days = set()
    for r in cursor.fetchall():
        ci, co = _as_date(r["check_in"]), _as_date(r["check_out"])
        last = co if co > ci else ci + timedelta(days=1)
        d = ci
        while d < last:
            days.add(d.isoformat())
            d += timedelta(days=1)
    return sorted(days)


def caretaker_visible_reservations(cursor, account_id, limit=None):
    """Rows for the caretaker DASHBOARD: customer bookings only, never walk-ins.
    Use this in your caretaker_dashboard route instead of your current reservations query."""
    schema = _walkin_schema(cursor)
    cursor.execute(
        f"""
        SELECT r.reservation_id, r.guest_name, r.check_in, r.check_out, r.guests, r.reservation_status,
               p.payment_status, p.amount_paid, {schema['proof_expr']} AS proof_of_payment
        FROM reservations r
        JOIN caretakers c ON c.resort_id = r.resort_id
        LEFT JOIN payments p ON p.payment_id = (
            SELECT p2.payment_id FROM payments p2
            WHERE p2.reservation_id = r.reservation_id
            ORDER BY p2.payment_id DESC LIMIT 1
        )
        WHERE c.account_id = %s AND c.status = 'Active' AND {_customer_visible_clause(schema)}
        ORDER BY r.created_at DESC, r.check_in DESC
        {'LIMIT ' + str(int(limit)) if limit else ''}
        """,
        (account_id,),
    )
    return cursor.fetchall()


@app.route("/caretaker-dashboard")
@role_required("caretaker")
def caretaker_dashboard():
    """Caretaker dashboard: customer bookings only. Walk-ins are never shown here (admin-only)."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        account_id = session.get("account_id")
        extra = ", r.description" if "description" in _table_columns(cursor, "resorts") else ""
        cursor.execute(
            f"""
            SELECT r.resort_id, r.resort_name, r.address, r.status{extra}
            FROM resorts r JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (account_id,),
        )
        resort = cursor.fetchone()
        if not resort:
            return redirect(url_for("login"))
        cursor.execute(
            "SELECT title, message, type, created_at FROM notifications "
            "WHERE account_id = %s ORDER BY created_at DESC LIMIT 5",
            (account_id,),
        )
        notifications = cursor.fetchall()
        rows = caretaker_visible_reservations(cursor, account_id, limit=30)
        today = date.today()
        for r in rows:
            r["nights"] = max((_as_date(r["check_out"]) - _as_date(r["check_in"])).days, 1)
            r["proof_url"] = url_for("static", filename=r["proof_of_payment"]) if r["proof_of_payment"] else None
            r["can_review"] = r["reservation_status"] == "Pending" and r["payment_status"] == "Pending"
        upcoming = [r for r in rows if r["reservation_status"] in ("Pending", "Confirmed")
                    and _as_date(r["check_out"]) >= today][:5]
        return render_template(
            "caretaker/caretaker_dashboard.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            notifications=notifications,
            reservations=rows,
            upcoming=upcoming,
            pending_count=sum(1 for r in rows if r["reservation_status"] == "Pending"),
            confirmed_count=sum(1 for r in rows if r["reservation_status"] == "Confirmed"),
        )
    finally:
        cursor.close()
        conn.close()


def _reservation_overview(cursor, account_id):
    """Customer reservations (online bookings) for the caretaker's resort + stat numbers."""
    schema = _walkin_schema(cursor)
    phone_col = "phone" if "phone" in _table_columns(cursor, "customers") else None
    parts = []
    if schema["contact"]:
        parts.append("r.guest_contact")
    if phone_col:
        parts.append(f"cu.{phone_col}")
    contact_expr = f"COALESCE({', '.join(parts)})" if parts else "NULL"
    cursor.execute(
        f"""
        SELECT r.reservation_id, COALESCE(NULLIF(r.guest_name, ''), a.fullname) AS customer_name,
               a.email, {contact_expr} AS contact, r.check_in, r.check_out, r.guests, r.reservation_status,
               CASE WHEN {schema['walkin_expr']} THEN 'Walk-in' ELSE 'Online' END AS booking_source,
               p.amount_paid, p.payment_status, p.payment_id, {schema['proof_expr']} AS proof_of_payment
        FROM reservations r
        JOIN caretakers c ON c.resort_id = r.resort_id
        LEFT JOIN customers cu ON cu.customer_id = r.customer_id
        LEFT JOIN accounts a ON a.account_id = cu.account_id
        LEFT JOIN payments p ON p.payment_id = (
            SELECT p2.payment_id FROM payments p2
            WHERE p2.reservation_id = r.reservation_id
            ORDER BY p2.payment_id DESC LIMIT 1
        )
        WHERE c.account_id = %s AND c.status = 'Active' AND ({_customer_visible_clause(schema)} OR r.reservation_status IN ('Confirmed', 'Completed'))
        ORDER BY r.created_at DESC, r.check_in DESC
        """,
        (account_id,),
    )
    today = date.today()
    stats = {"total": 0, "pending": 0, "upcoming": 0, "checked_in": 0}
    rows = []
    for r in cursor.fetchall():
        status = _stay_status(r, today)
        stats["total"] += 1
        if status == "Pending Verification":
            stats["pending"] += 1
        elif status == "Reserved":
            stats["upcoming"] += 1
        elif status == "Checked In":
            stats["checked_in"] += 1
        rows.append(
            {
                "id": r["reservation_id"],
                "booking": f"#RSV-{r['reservation_id']}",
                "customer": r["customer_name"] or "Customer",
                "email": "" if r["email"] == WALKIN_PLACEHOLDER_EMAIL else (r["email"] or ""),
                "source": r["booking_source"],
                "contact": r["contact"] or "",
                "check_in": str(r["check_in"]),
                "check_out": str(r["check_out"]),
                "guests": r["guests"],
                "amount": float(r["amount_paid"]) if r["amount_paid"] is not None else None,
                "payment_status": r["payment_status"],
                "proof": url_for("static", filename=r["proof_of_payment"]) if r["proof_of_payment"] else None,
                "status": status,
                "can_review": r["reservation_status"] == "Pending" and r["payment_status"] == "Pending" and bool(r["payment_id"]) and r["booking_source"] != "Walk-in",
            }
        )
    return {"stats": stats, "reservations": rows}


@app.route("/caretaker/inventory")
@role_required("caretaker")
def caretaker_inventory():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _walkin_resort(cursor)
        if not resort:
            return redirect(url_for("login"))
        return render_template(
            "caretaker/caretaker_inventory.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            data=_reservation_overview(cursor, session.get("account_id")),
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/caretaker/inventory/data")
@role_required("caretaker")
def caretaker_inventory_data():
    """JSON feed polled by the Reservations page so new customer bookings / admin changes appear live."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        return jsonify(_reservation_overview(cursor, session.get("account_id")))
    finally:
        cursor.close()
        conn.close()


MAINT_PRIORITIES = ("Low", "Normal", "High", "Urgent")
_MAINT_RE = re.compile(r"Resort: (.*?) \| Location: (.*?) \| Priority: (.*?) \| Reported by: (.*?)\n(.*)", re.S)


def _like_escape(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _notification_type(cursor, preferred):
    """Use `preferred` unless notifications.type is an ENUM that does not allow it (read-only check)."""
    cursor.execute(
        "SELECT COLUMN_TYPE AS t FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'notifications' AND COLUMN_NAME = 'type'"
    )
    row = cursor.fetchone() or {}
    t = row.get("t") or ""
    if t.lower().startswith("enum("):
        vals = [v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", t)]
        if preferred in vals:
            return preferred
        for v in vals:
            if "maint" in v.lower():
                return v
        for v in vals:
            if v.lower() in ("info", "general", "system", "update", "notice"):
                return v
        return vals[0] if vals else preferred
    return preferred


def _maintenance_overview(cursor, resort):
    stats = {"total": 0, "awaiting": 0, "seen": 0, "urgent": 0}
    rows = []
    owner_account = _owner_account_id(cursor, resort.get("owner_id"))
    if not owner_account:
        return {"stats": stats, "requests": rows}
    cursor.execute(
        "SELECT title, message, is_read, created_at FROM notifications "
        "WHERE account_id = %s AND title LIKE %s AND message LIKE %s ORDER BY created_at DESC",
        (owner_account, "Maintenance request:%", _like_escape(f"Resort: {resort['resort_name']} |") + "%"),
    )
    for r in cursor.fetchall():
        m = _MAINT_RE.match(r["message"] or "")
        if not m:
            continue
        seen = bool(r["is_read"])
        stats["total"] += 1
        stats["seen" if seen else "awaiting"] += 1
        if m.group(3) == "Urgent":
            stats["urgent"] += 1
        rows.append(
            {
                "issue": (r["title"] or "").replace("Maintenance request: ", "", 1),
                "location": m.group(2),
                "priority": m.group(3),
                "description": m.group(5).strip(),
                "status": "Seen by admin" if seen else "Awaiting admin",
                "reported": r["created_at"].strftime("%b %d, %Y") if r["created_at"] else "",
            }
        )
    return {"stats": stats, "requests": rows}


@app.route("/caretaker/maintenance", methods=["GET", "POST"])
@role_required("caretaker")
def caretaker_maintenance():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _walkin_resort(cursor)
        if not resort:
            return redirect(url_for("login"))
        if request.method == "POST":
            title = request.form.get("title", "").strip()[:100]
            location = request.form.get("location", "").strip()[:100].replace("|", "/")
            priority = request.form.get("priority", "Normal")
            description = request.form.get("description", "").strip()[:1000]
            if not title or not location or not description:
                flash("Issue title, location and description are required.", "warning")
            elif priority not in MAINT_PRIORITIES:
                flash("Choose a valid priority.", "warning")
            elif not _owner_account_id(cursor, resort["owner_id"]):
                flash("This resort has no admin assigned, so the request could not be sent.", "danger")
            else:
                try:
                    cursor.execute(
                        "INSERT INTO notifications (account_id, title, message, type) VALUES (%s, %s, %s, %s)",
                        (
                            _owner_account_id(cursor, resort["owner_id"]),
                            f"Maintenance request: {title}",
                            f"Resort: {resort['resort_name']} | Location: {location} | Priority: {priority} | "
                            f"Reported by: {session.get('fullname', 'Caretaker')}\n{description}",
                            _notification_type(cursor, "maintenance_request"),
                        ),
                    )
                    conn.commit()
                    flash("Maintenance request sent. The admin has been notified.", "success")
                except Exception as e:
                    conn.rollback()
                    print("MAINTENANCE ERROR:", e)
                    flash("The maintenance request could not be saved.", "danger")
            return redirect(url_for("caretaker_maintenance"))
        return render_template(
            "caretaker/caretaker_maintenance.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            data=_maintenance_overview(cursor, resort),
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/caretaker/maintenance/data")
@role_required("caretaker")
def caretaker_maintenance_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _walkin_resort(cursor)
        return jsonify(_maintenance_overview(cursor, resort) if resort else {"stats": {}, "requests": []})
    finally:
        cursor.close()
        conn.close()


@app.route("/caretaker/messages")
@role_required("caretaker")
def caretaker_messages():
    return caretaker_page("caretaker/caretaker_messages.html")

@app.route("/caretaker/notifications")
@role_required("caretaker")
def caretaker_notifications():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT title, message, type, is_read, created_at
            FROM notifications
            WHERE account_id = %s
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (session.get("account_id"),),
        )
        notifications = cursor.fetchall()
        return render_template(
            "caretaker/caretaker_notifications.html",
            fullname=session.get("fullname", "Caretaker"),
            notifications=notifications,
        )
    finally:
        cursor.close()
        conn.close()

@app.route("/caretaker/reports")
@role_required("caretaker")
def caretaker_reports():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.resort_id, r.resort_name, r.address, r.status
            FROM resorts r
            JOIN caretakers c ON c.resort_id = r.resort_id
            WHERE c.account_id = %s AND c.status = 'Active'
            """,
            (session.get("account_id"),),
        )
        resort = cursor.fetchone()
        if not resort:
            return redirect(url_for("login"))
        cursor.execute(
            """
            SELECT COUNT(*) AS bookings
            FROM reservations
            WHERE resort_id = %s
              AND created_at >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
            """,
            (resort["resort_id"],),
        )
        bookings = cursor.fetchone()["bookings"] or 0
        cursor.execute(
            """
            SELECT COALESCE(SUM(p.amount_paid), 0) AS revenue
            FROM payments p
            JOIN reservations r ON r.reservation_id = p.reservation_id
            WHERE r.resort_id = %s
              AND p.payment_status = 'Verified'
              AND p.payment_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
            """,
            (resort["resort_id"],),
        )
        revenue = cursor.fetchone()["revenue"] or 0
        return render_template(
            "caretaker/caretaker_reports.html",
            fullname=session.get("fullname", "Caretaker"),
            resort=resort,
            bookings=bookings,
            revenue=revenue,
        )
    finally:
        cursor.close()
        conn.close()

def _review_redirect():
    nxt = request.form.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for("caretaker_dashboard"))


@app.route("/caretaker/reservations/<int:reservation_id>/review", methods=["POST"])
@role_required("caretaker")
def caretaker_review_reservation(reservation_id):
    action = request.form.get("action")
    if action not in {"approve", "reject"}:
        flash("Invalid reservation action.", "warning")
        return _review_redirect()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        schema = _walkin_schema(cursor)
        cursor.execute(
            f"""
                 SELECT r.reservation_id, r.resort_id, r.check_in, r.check_out, cu.account_id AS customer_account_id,
                     r.reservation_status,
                   p.payment_id, p.payment_status
            FROM reservations r
            JOIN caretakers c ON c.resort_id = r.resort_id
                 JOIN customers cu ON cu.customer_id = r.customer_id
            LEFT JOIN payments p ON p.payment_id = (
                SELECT p2.payment_id
                FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC
                LIMIT 1
            )
            WHERE r.reservation_id = %s
              AND c.account_id = %s
              AND c.status = 'Active'
              AND {_customer_visible_clause(schema)}
            FOR UPDATE
            """,
            (reservation_id, session.get("account_id")),
        )
        reservation = cursor.fetchone()
        if not reservation:
            flash("Reservation not found for your assigned resort.", "danger")
            return _review_redirect()
        if reservation["reservation_status"] in {"Cancelled", "Rejected", "Completed"}:
            flash("This reservation can no longer be reviewed.", "warning")
            return _review_redirect()
        if not reservation["payment_id"]:
            flash("The customer has not submitted payment proof yet.", "warning")
            return _review_redirect()

        approved = action == "approve"
        if approved:
            clash = _dates_conflict(cursor, reservation["resort_id"], reservation["check_in"], reservation["check_out"], reservation_id)
            if clash:
                conn.rollback()
                flash("Cannot approve: those dates are " + _clash_text(clash) + ".", "warning")
                return _review_redirect()
        payment_status = "Verified" if approved else "Rejected"
        reservation_status = "Confirmed" if approved else "Rejected"
        cursor.execute(
            "UPDATE payments SET payment_status = %s WHERE payment_id = %s",
            (payment_status, reservation["payment_id"]),
        )
        cursor.execute(
            "UPDATE reservations SET reservation_status = %s WHERE reservation_id = %s",
            (reservation_status, reservation_id),
        )
        cursor.execute(
            """
            INSERT INTO notifications (account_id, title, message, type)
            VALUES (%s, %s, %s, %s)
            """,
            (
                reservation["customer_account_id"],
                "Reservation approved" if approved else "Reservation rejected",
                f"Your reservation #RSV-{reservation_id} was {'approved' if approved else 'rejected'} by the caretaker.",
                "reservation_approved" if approved else "reservation_rejected",
            ),
        )
        conn.commit()
        flash(
            "Reservation approved and payment verified." if approved else "Reservation rejected.",
            "success" if approved else "warning",
        )
    except Exception:
        conn.rollback()
        flash("The reservation review could not be saved.", "danger")
    finally:
        cursor.close()
        conn.close()

    return _review_redirect()

def send_email(to_email, subject, body_html):
    try:
        msg = Message(subject=subject, recipients=[to_email], html=body_html)
        mail.send(msg)
        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False

@app.route("/approve-caretaker/<int:account_id>")
@role_required("owner")
def approve_caretaker(account_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT a.account_id, a.fullname, a.email, a.approval_status,
                   c.resort_id, r.resort_name, r.owner_id
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            WHERE a.account_id = %s AND a.role = 'caretaker'
            """,
            (account_id,)
        )
        caretaker = cursor.fetchone()

        if not caretaker:
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        if caretaker["approval_status"] == "Approved":
            flash("Caretaker is already approved.", "warning")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            """
            UPDATE accounts
            SET account_status = 'Active', approval_status = 'Approved', is_verified = 1,
                approved_by = %s, approved_at = NOW()
            WHERE account_id = %s
            """,
            (session.get("user_id"), account_id)
        )

        cursor.execute(
            "UPDATE caretakers SET status = 'Active' WHERE account_id = %s",
            (account_id,)
        )
        conn.commit()

        login_link = url_for("login", _external=True)
        send_email(
            to_email=caretaker["email"],
            subject=f"You're Approved â€” {caretaker['resort_name']}",
            body_html=f"""
                <p>Hi {caretaker['fullname']},</p>
                <p>Your caretaker account for <strong>{caretaker['resort_name']}</strong> has been approved.</p>
                <p>You can now log in using your registered email and password.</p>
                <p><a href="{login_link}">Log In Here</a></p>
            """
        )

        flash(f"{caretaker['fullname']} approved. Login credentials sent via email.", "success")

    except Exception as e:
        conn.rollback()
        print("APPROVE ERROR:", e)
        flash("Error approving caretaker.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))

@app.route("/reject-caretaker/<int:account_id>")
@role_required("owner")
def reject_caretaker(account_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT a.fullname, r.owner_id
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            JOIN resorts r ON r.resort_id = c.resort_id
            WHERE a.account_id = %s
            """,
            (account_id,)
        )
        caretaker = cursor.fetchone()

        if not caretaker:
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            """
            UPDATE accounts
            SET account_status='Inactive', approval_status='Rejected', approved_by=%s, approved_at=NOW()
            WHERE account_id=%s
            """,
            (session.get("user_id"), account_id)
        )

        # Free up the resort so it reappears in the registration dropdown
        cursor.execute(
            "UPDATE caretakers SET status='Inactive' WHERE account_id=%s",
            (account_id,)
        )
        conn.commit()

        flash(f"{caretaker['fullname']} application rejected.", "warning")

    except Exception as e:
        conn.rollback()
        print("REJECT ERROR:", e)
        flash("Error rejecting caretaker.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/caretakers/<int:account_id>/update", methods=["POST"])
@role_required("owner")
def update_caretaker_account(account_id):
    fullname = request.form.get("fullname", "").strip()
    email = request.form.get("email", "").strip()
    new_password = request.form.get("new_password", "").strip()

    if not fullname or not email:
        flash("Caretaker name and email are required.", "warning")
        return redirect(url_for("admin_dashboard"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT a.account_id, a.email, a.fullname
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            WHERE a.account_id = %s AND a.role = 'caretaker'
            """,
            (account_id,),
        )
        caretaker = cursor.fetchone()
        if not caretaker:
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        if email != caretaker["email"]:
            cursor.execute("SELECT account_id FROM accounts WHERE email = %s AND account_id != %s", (email, account_id))
            if cursor.fetchone():
                flash("Another caretaker already uses this email.", "warning")
                return redirect(url_for("admin_dashboard"))

        if new_password and len(new_password) < 8:
            flash("New password must be at least 8 characters.", "warning")
            return redirect(url_for("admin_dashboard"))

        if new_password:
            cursor.execute(
                "UPDATE accounts SET fullname = %s, email = %s, password = %s WHERE account_id = %s AND role = 'caretaker'",
                (fullname, email, generate_password_hash(new_password), account_id),
            )
        else:
            cursor.execute(
                "UPDATE accounts SET fullname = %s, email = %s WHERE account_id = %s AND role = 'caretaker'",
                (fullname, email, account_id),
            )

        conn.commit()
        flash("Caretaker profile updated successfully.", "success")
    except Exception:
        conn.rollback()
        flash("Caretaker profile could not be updated.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/caretakers/<int:account_id>/delete", methods=["POST"])
@role_required("owner")
def delete_caretaker_account(account_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT a.account_id
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            WHERE a.account_id = %s AND a.role = 'caretaker'
            """,
            (account_id,),
        )
        if not cursor.fetchone():
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        cursor.execute("DELETE FROM caretakers WHERE account_id = %s", (account_id,))
        cursor.execute("DELETE FROM accounts WHERE account_id = %s AND role = 'caretaker'", (account_id,))
        conn.commit()
        flash("Caretaker deleted successfully.", "success")
    except Exception:
        conn.rollback()
        flash("Caretaker could not be deleted.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/caretakers/<int:account_id>/reset-password", methods=["POST"])
@role_required("owner")
def reset_caretaker_password(account_id):
    new_password = request.form.get("new_password", "")
    if len(new_password) < 8:
        flash("Caretaker password must be at least 8 characters.", "warning")
        return redirect(url_for("admin_dashboard"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT a.account_id
            FROM accounts a
            JOIN caretakers c ON c.account_id = a.account_id
            WHERE a.account_id = %s AND a.role = 'caretaker'
            """,
            (account_id,),
        )
        if not cursor.fetchone():
            flash("Caretaker account not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            "UPDATE accounts SET password = %s WHERE account_id = %s AND role = 'caretaker'",
            (generate_password_hash(new_password), account_id),
        )
        conn.commit()
        flash("Caretaker password reset successfully.", "success")
    except Exception:
        conn.rollback()
        flash("Caretaker password could not be reset.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# WALK-IN BOOKINGS
# Caretaker submits (guest details + total amount + photo) -> reservation is
# saved as Pending -> the resort owner/admin verifies it in /admin/walkins.
# ---------------------------------------------------------------------------
WALKIN_UPLOAD_SUBDIR = os.path.join("uploads", "walkin_proofs")
MAX_PROOF_BYTES = 5 * 1024 * 1024  # 5 MB


def _detect_image_ext(data):
    """Identify the real image type from its first bytes (not the filename)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _walkin_resort(cursor):
    cursor.execute(
        """
        SELECT r.resort_id, r.resort_name, r.address, r.status, r.owner_id
        FROM resorts r
        JOIN caretakers c ON c.resort_id = r.resort_id
        WHERE c.account_id = %s AND c.status = 'Active'
        """,
        (session.get("account_id"),),
    )
    return cursor.fetchone()


def _create_placeholder_customer(cursor):
    """Create the single shared 'Walk-in Guest' customer (one accounts row + one customers row) on first use.
    Only existing columns are used; the account gets a random password so nobody can log in with it."""
    acc_cols = _table_columns(cursor, "accounts")
    cus_cols = _table_columns(cursor, "customers")
    acc_values = {
        "fullname": "Walk-in Guest",
        "email": WALKIN_PLACEHOLDER_EMAIL,
        "password": generate_password_hash(uuid.uuid4().hex),
    }
    for column, value in (("role", "customer"), ("account_status", "Active"),
                          ("approval_status", "Approved"), ("is_verified", 1)):
        if column in acc_cols:
            acc_values[column] = value
    acc_now = ["created_at"] if "created_at" in acc_cols else []
    missing = _missing_required(acc_cols, set(acc_values) | set(acc_now))
    if missing:
        return None, ("accounts", missing)
    missing = _missing_required(cus_cols, {"account_id"})
    if missing:
        return None, ("customers", missing)
    account_id = _insert_row(cursor, "accounts", acc_values, acc_now)
    customer_id = _insert_row(cursor, "customers", {"account_id": account_id})
    return {"customer_id": customer_id, "account_id": account_id}, None


def _insert_row(cursor, table, values, now_columns=()):
    columns = list(values) + list(now_columns)
    placeholders = ["%s"] * len(values) + ["NOW()"] * len(now_columns)
    cursor.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
        tuple(values.values()),
    )
    return cursor.lastrowid


@app.route("/caretaker/walk-in", methods=["GET", "POST"])
@role_required("caretaker")
def caretaker_walkin():
    """Caretaker books on behalf of a walk-in guest. Uses only the columns your tables already have."""
    if request.method == "GET":
        return redirect(url_for("caretaker_guests"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    saved_path = None
    try:
        resort = _walkin_resort(cursor)
        if not resort:
            return redirect(url_for("login"))
        schema = _walkin_schema(cursor)
        errors = []

        # Guest: a linked customer account and/or a typed name
        guest_name = request.form.get("guest_name", "").strip()[:120]
        guest_contact = request.form.get("guest_contact", "").strip()[:30]
        customer = None
        raw_customer_id = request.form.get("customer_id", "").strip()
        if raw_customer_id:
            try:
                cursor.execute(
                    """
                    SELECT cu.customer_id, a.account_id, a.fullname
                    FROM customers cu
                    JOIN accounts a ON a.account_id = cu.account_id
                    WHERE cu.customer_id = %s AND a.account_status = 'Active'
                    """,
                    (int(raw_customer_id),),
                )
                customer = cursor.fetchone()
            except ValueError:
                customer = None
            if customer:
                guest_name = customer["fullname"]
            else:
                errors.append("That customer account could not be found.")
        elif not schema["name_only"]:
            errors.append(
                "Please link the customer's account. To book guests without an account, register one customer "
                f"account with the email {WALKIN_PLACEHOLDER_EMAIL} first."
            )
        elif not guest_name:
            errors.append("Enter the guest's name (or link their account).")

        if guest_contact and not re.fullmatch(r"[0-9+()\-\s]{7,20}", guest_contact):
            errors.append("Enter a valid phone number (digits, spaces, + - ( ) only).")
        elif not customer and not guest_contact:
            errors.append("Enter the guest's phone number.")

        try:
            check_in = datetime.strptime(request.form.get("check_in", ""), "%Y-%m-%d").date()
            check_out = datetime.strptime(request.form.get("check_out", ""), "%Y-%m-%d").date()
            if check_in < date.today():
                errors.append("Check-in date cannot be in the past.")
            if check_out < check_in:
                errors.append("Check-out date cannot be before check-in.")
            if check_in >= date.today() and check_out >= check_in:
                clash = _dates_conflict(cursor, resort["resort_id"], check_in, check_out)
                if clash:
                    errors.append("Those dates are " + _clash_text(clash) + ". Please choose other dates.")
        except ValueError:
            errors.append("Please provide valid check-in and check-out dates.")

        try:
            guests = int(request.form.get("guests", ""))
            if guests < 1:
                raise ValueError
        except ValueError:
            errors.append("Number of guests must be at least 1.")

        try:
            amount = Decimal(request.form.get("amount", "").strip()).quantize(Decimal("0.01"))
            if not amount.is_finite() or amount <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            errors.append("Total amount must be a number greater than 0.")

        proof = request.files.get("proof")
        image_data, ext = None, None
        if not schema["proof_table"]:
            errors.append("No proof_of_payment column was found in payments or reservations, so the photo cannot be stored.")
        elif not proof or not proof.filename:
            errors.append("A photo (proof of payment) is required.")
        else:
            image_data = proof.read(MAX_PROOF_BYTES + 1)
            if len(image_data) > MAX_PROOF_BYTES:
                errors.append("Photo is too large (maximum 5 MB).")
            else:
                ext = _detect_image_ext(image_data)
                if not ext:
                    errors.append("Photo must be a JPG, PNG or WEBP image.")

        if errors:
            for message in errors:
                flash(message, "warning")
            return redirect(url_for("caretaker_guests"))

        filename = f"{uuid.uuid4().hex}.{ext}"
        relative_path = f"uploads/walkin_proofs/{filename}"

        # Guest without an account (and no empty customer_id allowed): use the shared walk-in customer
        if not customer and not schema["account_optional"] and not schema["placeholder"]:
            schema["placeholder"], problem = _create_placeholder_customer(cursor)
            if problem:
                flash(
                    f"Could not create the shared walk-in guest account: the {problem[0]} table requires "
                    f"{', '.join(problem[1])}. Tell Claude what they should contain.",
                    "danger",
                )
                return redirect(url_for("caretaker_guests"))

        # No contact-number column: keep the phone number with the name, e.g. "Juan Dela Cruz (0917 123 4567)"
        stored_name = guest_name
        if guest_contact and not schema["contact"]:
            suffix = f" ({guest_contact})"
            maxlen = schema["res"].get("guest_name", {}).get("maxlen")
            if maxlen:
                stored_name = guest_name[: max(maxlen - len(suffix), 1)]
            stored_name += suffix

        # Only fill columns that exist in your tables
        res_values = {
            "resort_id": resort["resort_id"],
            "customer_id": customer["customer_id"] if customer else (schema["placeholder"]["customer_id"] if schema["placeholder"] else None),
            "guest_name": stored_name,
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
            "reservation_status": "Pending",
        }
        if schema["total"]:
            res_values["total_amount"] = amount
        if schema["contact"]:
            res_values["guest_contact"] = guest_contact or None
        if "booking_source" in schema["res"]:
            res_values["booking_source"] = "Walk-in"
        if schema["handled_by"]:
            res_values["handled_by"] = session.get("account_id")
        if schema["proof_table"] == "reservations":
            res_values["proof_of_payment"] = relative_path
        res_now = ["created_at"] if "created_at" in schema["res"] else []

        pay_values = {"amount_paid": amount, "payment_status": "Pending"}
        if schema["proof_table"] == "payments":
            pay_values["proof_of_payment"] = relative_path
        pay_now = ["payment_date"] if "payment_date" in schema["pay"] else []

        # Stop with a clear message (instead of a database error) if a required column can't be filled
        for table, columns, provided in (
            ("reservations", schema["res"], set(res_values) | set(res_now)),
            ("payments", schema["pay"], set(pay_values) | set(pay_now) | {"reservation_id"}),
        ):
            missing = _missing_required(columns, provided)
            if missing:
                flash(
                    f"Your {table} table has required columns this form does not fill: {', '.join(missing)}. "
                    "Tell Claude what they should contain.",
                    "danger",
                )
                return redirect(url_for("caretaker_guests"))

        # Save the photo, then the rows (file removed again if the database save fails)
        upload_dir = os.path.join(app.static_folder, WALKIN_UPLOAD_SUBDIR)
        os.makedirs(upload_dir, exist_ok=True)
        saved_path = os.path.join(upload_dir, filename)
        with open(saved_path, "wb") as fh:
            fh.write(image_data)

        reservation_id = _insert_row(cursor, "reservations", res_values, res_now)
        _insert_row(cursor, "payments", {"reservation_id": reservation_id, **pay_values}, pay_now)
        conn.commit()
        saved_path = None  # committed, keep the file

        # Best-effort notifications (never block the booking)
        try:
            cursor.execute(
                "INSERT INTO notifications (account_id, title, message, type) VALUES (%s, %s, %s, %s)",
                (
                    _owner_account_id(cursor, resort["owner_id"]) or resort["owner_id"],
                    "Walk-in booking awaiting verification",
                    f"{resort['resort_name']}: walk-in booking #RSV-{reservation_id} for {guest_name} "
                    f"(PHP {amount:,.2f}), booked by caretaker {session.get('fullname', '')}, needs your approval.",
                    "walkin_pending",
                ),
            )
            if customer:
                cursor.execute(
                    "INSERT INTO notifications (account_id, title, message, type) VALUES (%s, %s, %s, %s)",
                    (
                        customer["account_id"],
                        "Walk-in booking recorded",
                        f"Your walk-in booking #RSV-{reservation_id} at {resort['resort_name']} "
                        f"(PHP {amount:,.2f}) was recorded and is awaiting admin verification.",
                        "walkin_pending",
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()

        flash(f"Walk-in booking #RSV-{reservation_id} submitted. Waiting for admin verification.", "success")
    except Exception as e:
        conn.rollback()
        if saved_path and os.path.exists(saved_path):
            os.remove(saved_path)
        print("WALK-IN ERROR:", e)
        flash("The walk-in booking could not be saved.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("caretaker_guests"))


@app.route("/caretaker/walk-in/customers")
@role_required("caretaker")
def caretaker_walkin_customers():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT cu.customer_id, a.fullname, a.email
            FROM customers cu
            JOIN accounts a ON a.account_id = cu.account_id
            WHERE a.account_status = 'Active' AND (a.fullname LIKE %s OR a.email LIKE %s)
            ORDER BY a.fullname
            LIMIT 8
            """,
            (like, like),
        )
        return jsonify(
            [{"customer_id": r["customer_id"], "name": r["fullname"], "email": r["email"]} for r in cursor.fetchall()]
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/walkins")
@role_required("owner")
def admin_walkins():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        schema = _walkin_schema(cursor)
        contact_expr = "r.guest_contact" if schema["contact"] else "NULL"
        handled_expr = "h.fullname" if schema["handled_by"] else "NULL"
        handled_join = "LEFT JOIN accounts h ON h.account_id = r.handled_by" if schema["handled_by"] else ""
        cursor.execute(
            f"""
            SELECT r.reservation_id, rs.resort_name, r.guest_name, {contact_expr} AS guest_contact,
                   r.customer_id, r.check_in, r.check_out, r.guests, r.reservation_status, r.created_at,
                   {handled_expr} AS handled_by_name,
                   p.amount_paid, p.payment_status, {schema['proof_expr']} AS proof_of_payment
            FROM reservations r
            JOIN resorts rs ON rs.resort_id = r.resort_id
            {handled_join}
            LEFT JOIN payments p ON p.payment_id = (
                SELECT p2.payment_id FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC LIMIT 1
            )
            WHERE rs.owner_id = %s AND {schema['walkin_expr']}
            ORDER BY (r.reservation_status = 'Pending') DESC, r.created_at DESC
            """,
            (session.get("owner_id") or session.get("user_id"),),
        )
        return render_template(
            "admin/admin_walkins.html",
            walkins=cursor.fetchall(),
            placeholder_id=schema["placeholder"]["customer_id"] if schema["placeholder"] else None,
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/walkins/<int:reservation_id>/review", methods=["POST"])
@role_required("owner")
def admin_review_walkin(reservation_id):
    action = request.form.get("action")
    if action not in {"approve", "reject"}:
        flash("Invalid action.", "warning")
        return redirect(url_for("admin_walkins"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        schema = _walkin_schema(cursor)
        cursor.execute(
            f"""
            SELECT r.reservation_id, r.resort_id, r.check_in, r.check_out, r.reservation_status, p.payment_id,
                   cu.account_id AS customer_account_id
            FROM reservations r
            JOIN resorts rs ON rs.resort_id = r.resort_id
            LEFT JOIN customers cu ON cu.customer_id = r.customer_id
            LEFT JOIN payments p ON p.payment_id = (
                SELECT p2.payment_id FROM payments p2
                WHERE p2.reservation_id = r.reservation_id
                ORDER BY p2.payment_id DESC LIMIT 1
            )
            WHERE r.reservation_id = %s AND rs.owner_id = %s AND {schema['walkin_expr']}
            FOR UPDATE
            """,
            (reservation_id, session.get("owner_id") or session.get("user_id")),
        )
        booking = cursor.fetchone()
        if not booking:
            flash("Walk-in booking not found.", "danger")
            return redirect(url_for("admin_walkins"))
        if booking["reservation_status"] != "Pending" or not booking["payment_id"]:
            flash("This walk-in booking has already been reviewed.", "warning")
            return redirect(url_for("admin_walkins"))

        approved = action == "approve"
        if approved:
            clash = _dates_conflict(cursor, booking["resort_id"], booking["check_in"], booking["check_out"], reservation_id)
            if clash:
                conn.rollback()
                flash("Cannot approve: those dates are " + _clash_text(clash) + ". Reject this walk-in or ask for new dates.", "warning")
                return redirect(url_for("admin_walkins"))
        cursor.execute(
            "UPDATE payments SET payment_status = %s WHERE payment_id = %s",
            ("Verified" if approved else "Rejected", booking["payment_id"]),
        )
        cursor.execute(
            "UPDATE reservations SET reservation_status = %s WHERE reservation_id = %s",
            ("Confirmed" if approved else "Rejected", reservation_id),
        )
        cursor.execute(
            """
            INSERT INTO notifications (account_id, title, message, type)
            SELECT c.account_id, %s, %s, %s
            FROM caretakers c
            WHERE c.resort_id = %s AND c.status = 'Active'
            """,
            (
                "Walk-in booking approved" if approved else "Walk-in booking rejected",
                f"Walk-in booking #RSV-{reservation_id} was {'approved' if approved else 'rejected'} by the admin.",
                "walkin_approved" if approved else "walkin_rejected",
                booking["resort_id"],
            ),
        )
        shared_account = schema["placeholder"]["account_id"] if schema["placeholder"] else None
        if booking["customer_account_id"] and booking["customer_account_id"] != shared_account:  # no one to notify for guests without an account
            cursor.execute(
                "INSERT INTO notifications (account_id, title, message, type) VALUES (%s, %s, %s, %s)",
                (
                    booking["customer_account_id"],
                    "Walk-in booking approved" if approved else "Walk-in booking rejected",
                    f"Your walk-in booking #RSV-{reservation_id} was {'approved' if approved else 'rejected'} by the admin.",
                    "walkin_approved" if approved else "walkin_rejected",
                ),
            )
        conn.commit()
        flash(
            "Walk-in booking approved and payment verified." if approved else "Walk-in booking rejected.",
            "success" if approved else "warning",
        )
    except Exception as e:
        conn.rollback()
        print("WALK-IN REVIEW ERROR:", e)
        flash("The walk-in review could not be saved.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_walkins"))