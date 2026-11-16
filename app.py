import logging
import os
import secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort
from sqlalchemy import case, delete, func, select, text
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError, SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash

import settings
from database import build_engine, build_session_factory
from models import Product, User

MAX_PRICE = Decimal("9999999999.99")  # fits DECIMAL(12,2)
MAX_INT = 2_147_483_647               # fits MySQL INT
MYSQL_DUPLICATE_KEY = 1062

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# Configuration is validated here, so the app refuses to start without valid
# settings. No database connection is opened at import time.
_db_config = settings.load_database_config()
app.config["SECRET_KEY"] = settings.load_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Enable this when serving the app over HTTPS (COOKIE_SECURE=1):
app.config["SESSION_COOKIE_SECURE"] = settings.cookie_secure()

engine = build_engine(_db_config)
SessionLocal = build_session_factory(engine)
app.logger.info("Database configured: %s", _db_config.describe())


def get_db():
    """Return the SQLAlchemy session for the current request."""
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()  # rolls back anything uncommitted, returns connection to pool
        except SQLAlchemyError as exc:
            app.logger.warning("Error while closing database session: %s", type(exc).__name__)


def is_duplicate_key(exc):
    orig = getattr(exc, "orig", None)
    return bool(orig is not None and orig.args and orig.args[0] == MYSQL_DUPLICATE_KEY)


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(**kwargs)
    return wrapped_view


def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        sent = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, description="Invalid or missing security token. Refresh the page and try again.")


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/healthz")
def healthz():
    """Liveness + database check used by Docker HEALTHCHECK and Ansible."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        app.logger.error("Health check failed: %s", type(exc).__name__)
        return {"status": "database_unavailable"}, 503
    return {"status": "ok"}, 200


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(username) < 3 or len(username) > 40:
            flash("Username must be between 3 and 40 characters.", "danger")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            db = get_db()
            try:
                db.add(User(username=username, password_hash=generate_password_hash(password)))
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                if not is_duplicate_key(exc):
                    raise
                flash("That username is already taken.", "danger")
            else:
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            select(User.id, User.username, User.password_hash).where(User.username == username)
        ).first()

        if user is None or not check_password_hash(user.password_hash, password):
            flash("Invalid username or password.", "danger")
        else:
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            csrf_token()
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


def parse_product_form():
    sku = request.form.get("sku", "").strip().upper()
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip() or "General"
    try:
        price = Decimal(request.form.get("price", "").strip())
        quantity = int(request.form.get("quantity", ""))
        reorder_level = int(request.form.get("reorder_level", "5"))
    except (InvalidOperation, ValueError):
        raise ValueError("Price, quantity, and reorder level must be valid numbers.") from None

    if not price.is_finite():
        raise ValueError("Price, quantity, and reorder level must be valid numbers.")
    if not sku or len(sku) > 40:
        raise ValueError("SKU is required and must be 40 characters or fewer.")
    if not name or len(name) > 120:
        raise ValueError("Product name is required and must be 120 characters or fewer.")
    if len(category) > 80:
        raise ValueError("Category must be 80 characters or fewer.")
    if price < 0 or quantity < 0 or reorder_level < 0:
        raise ValueError("Price, quantity, and reorder level cannot be negative.")
    if price > MAX_PRICE or quantity > MAX_INT or reorder_level > MAX_INT:
        raise ValueError("Price, quantity, or reorder level is too large.")
    price = price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"sku": sku, "name": name, "category": category, "price": price,
            "quantity": quantity, "reorder_level": reorder_level}


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    uid = session["user_id"]
    low_stock = Product.quantity <= Product.reorder_level
    products = db.scalars(
        select(Product).where(Product.user_id == uid)
        .order_by(case((low_stock, 0), else_=1), Product.name, Product.id)
    ).all()
    row = db.execute(
        select(
            func.count(Product.id),
            func.coalesce(func.sum(Product.quantity), 0),
            func.coalesce(func.sum(Product.price * Product.quantity), 0),
            func.coalesce(func.sum(case((low_stock, 1), else_=0)), 0),
        ).where(Product.user_id == uid)
    ).one()
    stats = {
        "product_count": int(row[0]),
        "total_units": int(row[1]),
        "inventory_value": Decimal(row[2]),
        "low_stock_count": int(row[3]),
    }
    search = request.args.get("q", "").strip()
    category_filter = request.args.get("category", "").strip()
    if search:
        needle = search.casefold()
        products = [p for p in products if needle in p.name.casefold()
                    or needle in p.sku.casefold()
                    or needle in p.category.casefold()]
    if category_filter:
        products = [p for p in products if p.category == category_filter]
    categories = db.execute(
        select(Product.category).where(Product.user_id == uid)
        .distinct().order_by(Product.category)
    ).all()
    return render_template("dashboard.html", products=products, stats=stats, categories=categories,
                           search=search, category_filter=category_filter)


@app.route("/products/add", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        db = get_db()
        try:
            values = parse_product_form()
            db.add(Product(user_id=session["user_id"], **values))
            db.commit()
            flash("Product added successfully.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except IntegrityError as exc:
            db.rollback()
            if not is_duplicate_key(exc):
                raise
            flash("That SKU already exists in your inventory.", "danger")
    return render_template("product_form.html", product=None, page_title="Add product")


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    db = get_db()
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.user_id == session["user_id"])
    )
    if product is None:
        abort(404)

    if request.method == "POST":
        try:
            values = parse_product_form()
            for key, value in values.items():
                setattr(product, key, value)
            db.commit()
            flash("Product updated successfully.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except IntegrityError as exc:
            db.rollback()
            if not is_duplicate_key(exc):
                raise
            flash("That SKU is already used by another product.", "danger")
    return render_template("product_form.html", product=product, page_title="Edit product")


@app.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def delete_product(product_id):
    db = get_db()
    result = db.execute(
        delete(Product).where(Product.id == product_id, Product.user_id == session["user_id"])
    )
    db.commit()
    if result.rowcount:
        flash("Product deleted.", "success")
    else:
        flash("Product not found.", "warning")
    return redirect(url_for("dashboard"))


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "Bad request")), 400


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The requested page or product was not found."), 404


@app.errorhandler(SQLAlchemyError)
def database_error(error):
    """Turn database failures into a friendly page without leaking details.

    Connection problems return 503; the pool discards the broken connection
    (and pool_pre_ping validates the next one) so later requests recover once
    the database is back.
    """
    db = g.get("db")
    if db is not None:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
    orig = getattr(error, "orig", None)
    app.logger.error("Database error: %s%s", type(error).__name__,
                     f" ({type(orig).__name__}: {orig})" if orig is not None else "")
    if isinstance(error, (OperationalError, InterfaceError)) or getattr(error, "connection_invalidated", False):
        return render_template(
            "error.html", code=503,
            message="The database is temporarily unavailable. Please try again in a moment."), 503
    return render_template("error.html", code=500, message="An unexpected database error occurred."), 500


if __name__ == "__main__":
    # Development server only. Production uses Gunicorn (see Dockerfile).
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
