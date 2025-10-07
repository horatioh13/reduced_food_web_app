from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy import text
from werkzeug.utils import secure_filename
import os
import uuid
from functools import wraps
import requests
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
from PIL import Image, ImageOps
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()  # NEW: loads .env so SECRET_KEY is available

# Ensure instance is inside the project directory, not $HOME
project_root = os.path.dirname(__file__)

app = Flask(
    __name__,
    instance_path=os.path.join(project_root, "instance"),
    instance_relative_config=False,
    static_url_path='/reducedfood/static',  # <-- tell Flask where static files live
    static_folder='static',
    template_folder='templates'
)

app.config['APPLICATION_ROOT'] = '/reducedfood'
app.config['SERVER_NAME'] = 'makerspace.su.bath.ac.uk'


# Create the instance and uploads folder if missing
if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path, exist_ok=True)
uploads_path = os.path.join(app.instance_path, 'uploads')
if not os.path.exists(uploads_path):
    os.makedirs(uploads_path, exist_ok=True)

app.config['SECRET_KEY'] = os.environ['SECRET_KEY']  # require env var
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'reduced_food.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads')
# Secure cookies in production
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# CSRF protection for all POST requests
csrf = CSRFProtect(app)

db = SQLAlchemy(app)

# Make csrf_token() available in templates (for non-WTF forms)
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

class Place(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    average_rating = db.Column(db.Float, default=0.0)
    deal_hours = db.Column(db.String(255))
    photo_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    reviews = db.relationship('Review', backref='place', cascade='all, delete-orphan', lazy=True)

    @property
    def all_photo_filenames(self):
        names = []
        if self.photo_filename:
            names.append(self.photo_filename)
        names.extend([r.photo_filename for r in self.reviews if r.photo_filename])
        return names


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.Integer, db.ForeignKey('place.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    photo_filename = db.Column(db.String(255))


# Flask 3.x removed before_first_request; initialize DB at startup instead
def init_db():
    with app.app_context():
        # Ensure uploads directory exists (now under instance/)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # Create tables
        db.create_all()

        # Lightweight column adds for existing SQLite DBs (no migrations)
        try:
            db.session.execute(text('ALTER TABLE place ADD COLUMN deal_hours VARCHAR(255)'))
        except Exception:
            pass
        try:
            db.session.execute(text('ALTER TABLE place ADD COLUMN photo_filename VARCHAR(255)'))
        except Exception:
            pass
        try:
            db.session.execute(text('ALTER TABLE review ADD COLUMN photo_filename VARCHAR(255)'))
        except Exception:
            pass
        try:
            db.session.execute(text('ALTER TABLE place ADD COLUMN created_at DATETIME'))
        except Exception:
            pass
        db.session.commit()


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def _save_upload(file_storage):
    """
    Validate and save an uploaded image to instance/uploads; return stored filename.
    Returns None if no file or invalid image.
    - Verifies real image content (not just extension)
    - Strips EXIF and fixes orientation
    - Resizes to max 1600px on the longest side
    """
    if not file_storage or not getattr(file_storage, 'filename', None):
        return None

    filename = secure_filename(file_storage.filename or "")
    if not filename:
        return None

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        flash("Invalid image type. Allowed: png, jpg, jpeg, gif", "warning")
        return None

    try:
        # Verify image content
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as im_verify:
            im_verify.verify()

        # Re-open for processing
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as im:
            # Normalize orientation and strip metadata
            im = ImageOps.exif_transpose(im)

            # Resize down if needed
            MAX_DIM = 1600
            im.thumbnail((MAX_DIM, MAX_DIM))

            # Choose final format/extension
            fmt = (im.format or "").upper()
            if fmt not in ("JPEG", "PNG", "GIF"):
                fmt = "JPEG"
            ext_map = {"JPEG": "jpg", "PNG": "png", "GIF": "gif"}
            out_ext = ext_map[fmt]

            unique_name = f"{uuid.uuid4().hex}.{out_ext}"
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)

            # Convert modes and save with sensible defaults
            if fmt == "JPEG":
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.save(save_path, format="JPEG", quality=85, optimize=True)
            elif fmt == "PNG":
                im.save(save_path, format="PNG", optimize=True)
            else:  # GIF
                im.save(save_path, format="GIF")

        return unique_name

    except Exception:
        flash("Uploaded file is not a valid image.", "warning")
        return None


# --- CAS auth (University of Bath) ---
CAS_BASE = os.environ.get('CAS_BASE', 'https://auth.bath.ac.uk')
CAS_LOGIN_ROUTE = os.environ.get('CAS_LOGIN_ROUTE', '/login')
CAS_VALIDATE_ROUTE = os.environ.get('CAS_VALIDATE_ROUTE', '/serviceValidate')

def cas_validate(ticket: str, service: str):
    try:
        resp = requests.get(f"{CAS_BASE}{CAS_VALIDATE_ROUTE}", params={'service': service, 'ticket': ticket}, timeout=5)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        # Try with namespace, then fall back
        user_el = root.find('.//{http://www.yale.edu/tp/cas}authenticationSuccess/{http://www.yale.edu/tp/cas}user')
        if user_el is None:
            ns = {'cas': 'http://www.yale.edu/tp/cas'}
            user_el = root.find('.//cas:authenticationSuccess/cas:user', ns)
        if user_el is None:
            user_el = root.find('.//user')
        return user_el.text.strip() if user_el is not None and user_el.text else None
    except Exception:
        return None

def login_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get('user'):
            session['next'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return _wrap

@app.route('/login')
def login():
    ticket = request.args.get('ticket')

    # Full service URL must include /reducedfood/login for CAS to redirect back correctly
    service = f"https://makerspace.su.bath.ac.uk/reducedfood/login"

    if not ticket:
        # Redirect user to CAS login
        return redirect(f"{CAS_BASE}{CAS_LOGIN_ROUTE}?service={quote_plus(service)}")

    # Validate the ticket from CAS
    user = cas_validate(ticket, service)
    if user:
        session['user'] = user
        flash(f'Logged in as {user}', 'success')
        nxt = session.pop('next', None) or url_for('index')
        return redirect(nxt)

    flash('CAS login failed. Please try again.', 'danger')
    return redirect(url_for('index'))



@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))


# NOTE: Images uploaded via the forms are saved to disk under `static/uploads/`.
# Only the generated filename (path relative to static/) is stored in the SQLite
# database (Place.photo_filename and Review.photo_filename). The DB does NOT
# store the binary image data itself. This keeps the database small and avoids
# bloating the .db file with large blobs.


@app.route('/')
def index():
    places = Place.query.order_by(Place.name.asc()).all()
    return render_template('index.html', places=places)


@app.route('/places', methods=['POST'])
@login_required
def add_place():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    deal_hours = request.form.get('deal_hours', '').strip()
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    photo = request.files.get('place_photo')

    error = None
    if not name:
        error = 'Name is required.'
    elif not description:
        error = 'Description is required.'
    elif lat is None or lng is None:
        error = 'Location is required (click on the map to set it).'

    if error:
        flash(error, 'danger')
        return redirect(url_for('index'))

    try:
        latitude = float(lat)
        longitude = float(lng)
    except ValueError:
        flash('Invalid coordinates provided.', 'danger')
        return redirect(url_for('index'))

    # Check duplicates by name
    if Place.query.filter_by(name=name).first():
        flash('A place with that name already exists.', 'warning')
        return redirect(url_for('index'))

    photo_filename = _save_upload(photo)
    place = Place(
        name=name,
        description=description,
        latitude=latitude,
        longitude=longitude,
        deal_hours=deal_hours or None,
        photo_filename=photo_filename,
    )
    db.session.add(place)
    db.session.commit()
    flash('Place added successfully!', 'success')
    return redirect(url_for('index'))


@app.route('/places/<int:place_id>/reviews', methods=['POST'])
@login_required
def add_review(place_id):
    place = Place.query.get_or_404(place_id)
    rating = request.form.get('rating')
    text = request.form.get('text', '').strip()
    photo = request.files.get('photo')

    try:
        rating_val = int(rating)
    except (TypeError, ValueError):
        flash('Rating must be an integer between 1 and 5.', 'danger')
        return redirect(url_for('index'))

    if rating_val < 1 or rating_val > 5:
        flash('Rating must be between 1 and 5.', 'danger')
        return redirect(url_for('index'))

    if not text:
        flash('Review text is required.', 'danger')
        return redirect(url_for('index'))

    review = Review(place_id=place.id, rating=rating_val, text=text, photo_filename=_save_upload(photo))
    db.session.add(review)

    # Recalculate average rating
    ratings = [r.rating for r in place.reviews] + [rating_val]
    place.average_rating = sum(ratings) / len(ratings)

    db.session.commit()
    flash('Review added. Thanks!', 'success')
    return redirect(url_for('index'))


# Serve uploaded files from the instance uploads directory
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.after_request
def set_security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    resp.headers['Permissions-Policy'] = 'geolocation=()'
    resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    resp.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: blob:; script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; connect-src 'self' https://router.project-osrm.org; frame-ancestors 'self';"
    return resp

def create_app():
    init_db()
    # Ensure Flask sees correct script name when behind a reverse proxy
    # nginx will set X-Forwarded-Prefix to the mounted path (/reducedfood)
    class PrefixMiddleware:
        def __init__(self, app):
            self.app = app

        def __call__(self, environ, start_response):
            # If the proxy provided a prefix header, set SCRIPT_NAME so
            # url_for and redirects generate URLs with the prefix.
            prefix = environ.get('HTTP_X_FORWARDED_PREFIX', '')
            if prefix:
                environ['SCRIPT_NAME'] = prefix.rstrip('/')
                # Adjust PATH_INFO if it also contains the prefix
                path = environ.get('PATH_INFO', '')
                if path.startswith(prefix):
                    environ['PATH_INFO'] = path[len(prefix):] or '/'
            return self.app(environ, start_response)

    # Apply ProxyFix to trust forwarded headers from nginx (one proxy hop)
    proxied = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.wsgi_app = PrefixMiddleware(proxied)

    return app

# Make the module-level "app" the wrapped app so Gunicorn imports the correct WSGI app
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    