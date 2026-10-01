"""Admin (owner) Property Manager.
Per property: reports, bookings, maintenance requests, edit details/prices/amenities, post updates, change status.
Uses only existing tables/columns (resorts, reservations, payments, customers, accounts, caretakers, owners,
notifications, and `reviews` if it exists). Nothing is created or altered in the database."""
import re
import calendar as _calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.routing import BuildError

from templates.admin.app import app
from config import get_connection
from models.decorators import role_required
from routes.caretaker import _walkin_schema, _stay_status, _as_date, _table_columns, _owner_account_id

_MAINT_RE = re.compile(r"Resort: (.*?) \| Location: (.*?) \| Priority: (.*?) \| Reported by: (.*?)\n(.*)", re.S)
TEXT_FIELDS = ("resort_name", "address", "email", "phone", "amenities", "description")


# ----------------------------------------------------------------------------- helpers
def _owner_id(cursor):
    if session.get("owner_id"):
        return session["owner_id"]
    cursor.execute("SELECT owner_id FROM owners WHERE account_id = %s", (session.get("account_id"),))
    row = cursor.fetchone()
    return row["owner_id"] if row else None


def _owned_resort(cursor, resort_id):
    cursor.execute("SELECT * FROM resorts WHERE resort_id = %s AND owner_id = %s", (resort_id, _owner_id(cursor)))
    return cursor.fetchone()


def _price_columns(cursor):
    return [c for c in _table_columns(cursor, "resorts") if re.search(r"price|rate", c, re.I) and not re.search(r"rating|rated", c, re.I)]


def _f(v):
    return float(v) if v is not None else None


def _d(v):
    return str(v)[:10] if v else ""


def _month(arg):
    try:
        y, m = (int(x) for x in (arg or "").split("-"))
        first = date(y, m, 1)
    except (ValueError, TypeError):
        first = date.today().replace(day=1)
    nxt = date(first.year + (first.month == 12), 1 if first.month == 12 else first.month + 1, 1)
    return first, nxt


def _like_escape(v):
    return v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _notification_type(cursor, preferred):
    cursor.execute(
        "SELECT COLUMN_TYPE AS t FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'notifications' AND COLUMN_NAME = 'type'"
    )
    t = (cursor.fetchone() or {}).get("t") or ""
    if t.lower().startswith("enum("):
        vals = [v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", t)]
        if preferred in vals:
            return preferred
        for v in vals:
            if v.lower() in ("info", "general", "system", "update", "notice") or "update" in v.lower():
                return v
        return vals[0] if vals else preferred
    return preferred


def _caretaker_accounts(cursor, resort_id):
    cursor.execute("SELECT account_id FROM caretakers WHERE resort_id = %s AND status = 'Active'", (resort_id,))
    return [r["account_id"] for r in cursor.fetchall()]


def _notify_caretakers(cursor, resort_id, title, message, ntype):
    ids = _caretaker_accounts(cursor, resort_id)
    t = _notification_type(cursor, ntype)
    for acc in ids:
        cursor.execute(
            "INSERT INTO notifications (account_id, title, message, type) VALUES (%s, %s, %s, %s)", (acc, title, message, t)
        )
    return len(ids)


def _back(resort_id, tab):
    return redirect(url_for("admin_property_detail", resort_id=resort_id, tab=tab))


# ----------------------------------------------------------------------------- data builders
def _maintenance(cursor, resort):
    owner_acc = _owner_account_id(cursor, resort["owner_id"])
    if not owner_acc:
        return []
    cursor.execute(
        "SELECT notification_id, title, message, is_read, created_at FROM notifications "
        "WHERE account_id = %s AND title LIKE %s AND message LIKE %s ORDER BY created_at DESC LIMIT 100",
        (owner_acc, "Maintenance request:%", _like_escape(f"Resort: {resort['resort_name']} |") + "%"),
    )
    out = []
    for r in cursor.fetchall():
        m = _MAINT_RE.match(r["message"] or "")
        if not m:
            continue
        out.append({
            "id": r["notification_id"], "issue": (r["title"] or "").replace("Maintenance request: ", "", 1),
            "location": m.group(2), "priority": m.group(3), "reported_by": m.group(4), "description": m.group(5).strip(),
            "seen": bool(r["is_read"]), "reported": r["created_at"].strftime("%b %d, %Y %I:%M %p") if r["created_at"] else "",
        })
    return out


def _bookings(cursor, resort_id):
    schema = _walkin_schema(cursor)
    total = "r.total_amount" if schema["total"] else "NULL"
    cursor.execute(
        f"""
        SELECT r.reservation_id, COALESCE(NULLIF(r.guest_name, ''), a.fullname) AS guest, a.email,
               r.check_in, r.check_out, r.guests, r.reservation_status, {total} AS total_amount,
               CASE WHEN {schema['walkin_expr']} THEN 'Walk-in' ELSE 'Online' END AS source,
               p.amount_paid, p.payment_status, {schema['proof_expr']} AS proof
        FROM reservations r
        LEFT JOIN customers cu ON cu.customer_id = r.customer_id
        LEFT JOIN accounts a ON a.account_id = cu.account_id
        LEFT JOIN payments p ON p.payment_id = (
            SELECT p2.payment_id FROM payments p2 WHERE p2.reservation_id = r.reservation_id ORDER BY p2.payment_id DESC LIMIT 1)
        WHERE r.resort_id = %s
        ORDER BY r.created_at DESC, r.check_in DESC LIMIT 300
        """,
        (resort_id,),
    )
    today, out = date.today(), []
    for r in cursor.fetchall():
        out.append({
            "id": r["reservation_id"], "booking": f"#RSV-{r['reservation_id']}", "guest": r["guest"] or "Guest",
            "email": "" if r["email"] == "walkin.guest@pansolresorts.com" else (r["email"] or ""),
            "check_in": _d(r["check_in"]), "check_out": _d(r["check_out"]), "guests": r["guests"], "source": r["source"],
            "amount": _f(r["amount_paid"] if r["amount_paid"] is not None else r["total_amount"]),
            "payment_status": r["payment_status"], "proof": url_for("static", filename=r["proof"]) if r["proof"] else None,
            "status": _stay_status(r, today), "raw_status": r["reservation_status"],
        })
    return out


def _reports(cursor, resort_id, first, nxt):
    cursor.execute(
        "SELECT reservation_status, COUNT(*) AS n FROM reservations WHERE resort_id = %s AND check_in >= %s AND check_in < %s "
        "GROUP BY reservation_status", (resort_id, first, nxt))
    by_status = {r["reservation_status"]: r["n"] for r in cursor.fetchall()}
    cursor.execute(
        "SELECT COALESCE(SUM(p.amount_paid), 0) AS rev FROM payments p JOIN reservations r ON r.reservation_id = p.reservation_id "
        "WHERE r.resort_id = %s AND p.payment_status = 'Verified' AND p.payment_date >= %s AND p.payment_date < %s",
        (resort_id, first, nxt))
    revenue = _f(cursor.fetchone()["rev"]) or 0.0
    cursor.execute(
        "SELECT check_in, check_out FROM reservations WHERE resort_id = %s AND reservation_status IN ('Confirmed', 'Completed') "
        "AND check_in < %s AND GREATEST(check_out, DATE_ADD(check_in, INTERVAL 1 DAY)) > %s", (resort_id, nxt, first))
    days = set()
    for r in cursor.fetchall():
        ci, co = _as_date(r["check_in"]), _as_date(r["check_out"])
        d = ci
        while d < (co if co > ci else ci + timedelta(days=1)):
            if first <= d < nxt:
                days.add(d)
            d += timedelta(days=1)
    in_month = _calendar.monthrange(first.year, first.month)[1]
    rating = reviews = None
    rc = _table_columns(cursor, "reviews")
    if "rating" in rc and "resort_id" in rc:
        cursor.execute("SELECT AVG(rating) AS a, COUNT(*) AS n FROM reviews WHERE resort_id = %s", (resort_id,))
        row = cursor.fetchone()
        rating, reviews = (round(float(row["a"]), 1) if row["a"] is not None else None), row["n"]
    start = (first.replace(day=1) - timedelta(days=150)).replace(day=1)
    cursor.execute(
        "SELECT DATE_FORMAT(p.payment_date, '%%Y-%%m') AS m, COALESCE(SUM(p.amount_paid), 0) AS rev FROM payments p "
        "JOIN reservations r ON r.reservation_id = p.reservation_id WHERE r.resort_id = %s AND p.payment_status = 'Verified' "
        "AND p.payment_date >= %s GROUP BY m", (resort_id, start))
    rev_map = {r["m"]: _f(r["rev"]) for r in cursor.fetchall()}
    trend, y, m = [], first.year, first.month
    for i in range(5, -1, -1):
        yy, mm = y, m - i
        while mm < 1:
            mm += 12
            yy -= 1
        key = f"{yy}-{mm:02d}"
        trend.append({"label": date(yy, mm, 1).strftime("%b"), "revenue": rev_map.get(key, 0.0)})
    return {
        "month": first.strftime("%Y-%m"), "month_label": first.strftime("%B %Y"),
        "bookings": sum(v for k, v in by_status.items() if k not in ("Rejected", "Cancelled")),
        "confirmed": by_status.get("Confirmed", 0) + by_status.get("Completed", 0), "pending": by_status.get("Pending", 0),
        "cancelled": by_status.get("Rejected", 0) + by_status.get("Cancelled", 0),
        "revenue": revenue, "occupancy": round(len(days) / in_month * 100), "rating": rating, "reviews": reviews, "trend": trend,
    }


def _updates(cursor, resort_id):
    cursor.execute(
        "SELECT DISTINCT n.title, n.message, n.created_at FROM notifications n JOIN caretakers c ON c.account_id = n.account_id "
        "WHERE c.resort_id = %s AND n.title LIKE %s ORDER BY n.created_at DESC LIMIT 10", (resort_id, "Resort update:%"))
    return [{"title": r["title"].replace("Resort update: ", "", 1), "message": r["message"],
             "date": r["created_at"].strftime("%b %d, %Y %I:%M %p") if r["created_at"] else ""} for r in cursor.fetchall()]


def _detail_state(cursor, resort, month_arg):
    first, nxt = _month(month_arg)
    return {"reports": _reports(cursor, resort["resort_id"], first, nxt), "bookings": _bookings(cursor, resort["resort_id"]),
            "maintenance": _maintenance(cursor, resort), "updates": _updates(cursor, resort["resort_id"])}


# ----------------------------------------------------------------------------- pages
@app.route("/admin/manage-properties")
@role_required("owner")
def admin_properties_manage():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        first, nxt = _month(None)
        cursor.execute("SELECT * FROM resorts WHERE owner_id = %s ORDER BY resort_name", (_owner_id(cursor),))
        cards = []
        for r in cursor.fetchall():
            rep = _reports(cursor, r["resort_id"], first, nxt)
            cards.append({
                "id": r["resort_id"], "name": r["resort_name"], "address": r.get("address") or "No address provided",
                "contact": r.get("email") or r.get("phone") or "No contact details", "status": r.get("status") or "Active",
                "bookings": rep["bookings"], "pending": rep["pending"], "revenue": rep["revenue"], "occupancy": rep["occupancy"],
                "open_maintenance": sum(1 for m in _maintenance(cursor, r) if not m["seen"]),
            })
        return render_template("admin/admin_properties_manage.html", cards=cards, username=session.get("fullname", "Owner"),
                               month_label=first.strftime("%B %Y"))
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/manage-properties/<int:resort_id>")
@role_required("owner")
def admin_property_detail(resort_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _owned_resort(cursor, resort_id)
        if not resort:
            flash("Property not found.", "warning")
            return redirect(url_for("admin_properties_manage"))
        cols = _table_columns(cursor, "resorts")
        urls = {}
        for key, ep in (("review", "reservation_detail"), ("walkin", "admin_review_walkin"), ("walkins", "admin_walkins")):
            try:
                urls[key] = url_for(ep, **({"reservation_id": 0} if ep != "admin_walkins" else {}))
            except BuildError:
                urls[key] = None
        return render_template(
            "admin/admin_property_detail.html", username=session.get("fullname", "Owner"),
            resort={k: (_f(v) if isinstance(v, Decimal) else v) for k, v in resort.items() if k != "logo"},
            text_fields=[c for c in TEXT_FIELDS if c in cols], price_fields=_price_columns(cursor),
            state=_detail_state(cursor, resort, request.args.get("month")), urls=urls,
            tab=request.args.get("tab", "overview"),
            seen_url=url_for("admin_maintenance_seen", notification_id=0),
        )
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/manage-properties/<int:resort_id>/data")
@role_required("owner")
def admin_property_data(resort_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _owned_resort(cursor, resort_id)
        if not resort:
            return jsonify({"error": "not found"}), 404
        return jsonify(_detail_state(cursor, resort, request.args.get("month")))
    finally:
        cursor.close()
        conn.close()


# ----------------------------------------------------------------------------- actions
@app.route("/admin/manage-properties/<int:resort_id>/details", methods=["POST"])
@role_required("owner")
def admin_property_save(resort_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _owned_resort(cursor, resort_id)
        if not resort:
            flash("Property not found.", "warning")
            return redirect(url_for("admin_properties_manage"))
        cols = _table_columns(cursor, "resorts")
        sets, vals = [], []
        name = request.form.get("resort_name", "").strip()[:150]
        if "resort_name" in cols:
            if not name:
                flash("Property name is required.", "warning")
                return _back(resort_id, "edit")
            sets.append("resort_name = %s"); vals.append(name)
        for col, limit in (("address", 255), ("phone", 20), ("amenities", 500), ("description", 2000)):
            if col in cols and col in request.form:
                sets.append(f"{col} = %s"); vals.append(request.form[col].strip()[:limit] or None)
        if "email" in cols and "email" in request.form:
            email = request.form["email"].strip()[:150]
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                flash("Enter a valid contact email.", "warning")
                return _back(resort_id, "edit")
            sets.append("email = %s"); vals.append(email or None)
        for col in _price_columns(cursor):
            raw = request.form.get(col, "").strip()
            if raw == "":
                continue
            try:
                price = Decimal(raw).quantize(Decimal("0.01"))
                if price < 0 or not price.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                flash(f"{col.replace('_', ' ').title()} must be a valid amount.", "warning")
                return _back(resort_id, "edit")
            sets.append(f"{col} = %s"); vals.append(price)
        if sets:
            cursor.execute(f"UPDATE resorts SET {', '.join(sets)} WHERE resort_id = %s AND owner_id = %s",
                           (*vals, resort_id, resort["owner_id"]))
            conn.commit()
        flash("Property details saved. Customers and the caretaker now see the new details.", "success")
    except Exception as e:
        conn.rollback()
        print("PROPERTY SAVE ERROR:", e)
        flash("The property could not be saved.", "danger")
    finally:
        cursor.close()
        conn.close()
    return _back(resort_id, "edit")


@app.route("/admin/manage-properties/<int:resort_id>/status", methods=["POST"])
@role_required("owner")
def admin_property_status(resort_id):
    status = request.form.get("status")
    nxt_page = request.form.get("next", "detail")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _owned_resort(cursor, resort_id)
        if not resort or status not in ("Active", "Inactive"):
            flash("Invalid property or status.", "warning")
            return redirect(url_for("admin_properties_manage"))
        cursor.execute("UPDATE resorts SET status = %s WHERE resort_id = %s AND owner_id = %s", (status, resort_id, resort["owner_id"]))
        _notify_caretakers(cursor, resort_id, f"Resort update: {resort['resort_name']} is now {status}",
                           f"The admin set {resort['resort_name']} to {status}."
                           + (" It is hidden from customers and cannot be booked." if status == "Inactive" else " It is visible to customers again."),
                           "resort_update")
        conn.commit()
        msg = f"{resort['resort_name']} is now {status}."
        if status == "Inactive":
            cursor.execute("SELECT COUNT(*) AS n FROM reservations WHERE resort_id = %s AND reservation_status = 'Confirmed' AND check_out >= CURDATE()", (resort_id,))
            n = cursor.fetchone()["n"]
            if n:
                msg += f" Note: {n} confirmed upcoming booking(s) still exist."
        flash(msg, "success")
    except Exception as e:
        conn.rollback()
        print("STATUS ERROR:", e)
        flash("The status could not be changed.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("admin_properties_manage")) if nxt_page == "list" else _back(resort_id, "overview")


@app.route("/admin/manage-properties/<int:resort_id>/update", methods=["POST"])
@role_required("owner")
def admin_property_post_update(resort_id):
    title = request.form.get("title", "").strip()[:100]
    message = request.form.get("message", "").strip()[:1000]
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        resort = _owned_resort(cursor, resort_id)
        if not resort:
            flash("Property not found.", "warning")
            return redirect(url_for("admin_properties_manage"))
        if not title or not message:
            flash("Update title and details are required.", "warning")
        elif not _caretaker_accounts(cursor, resort_id):
            flash("No active caretaker is assigned to this property, so nobody would receive the update.", "warning")
        else:
            n = _notify_caretakers(cursor, resort_id, f"Resort update: {title}", message, "resort_update")
            conn.commit()
            flash(f"Update posted. {n} caretaker(s) will see it on their Updates page.", "success")
    except Exception as e:
        conn.rollback()
        print("UPDATE POST ERROR:", e)
        flash("The update could not be posted.", "danger")
    finally:
        cursor.close()
        conn.close()
    return _back(resort_id, "updates")


@app.route("/admin/maintenance/<int:notification_id>/seen", methods=["POST"])
@role_required("owner")
def admin_maintenance_seen(notification_id):
    resort_id = request.form.get("resort_id", type=int)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT owner_id FROM owners WHERE owner_id = %s", (_owner_id(cursor),))
        owner_row = cursor.fetchone()
        owner_acc = _owner_account_id(cursor, owner_row["owner_id"]) if owner_row else None
        if owner_acc:
            cursor.execute("UPDATE notifications SET is_read = 1 WHERE notification_id = %s AND account_id = %s", (notification_id, owner_acc))
            conn.commit()
            flash("Marked as seen. The caretaker can now see it was acknowledged.", "success")
    except Exception as e:
        conn.rollback()
        print("MAINT SEEN ERROR:", e)
        flash("Could not update the request.", "danger")
    finally:
        cursor.close()
        conn.close()
    return _back(resort_id, "maintenance") if resort_id else redirect(url_for("admin_properties_manage"))
