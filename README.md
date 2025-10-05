# Bath Reduced Food Deals (Flask)

A simple local Flask app to crowdsource places in Bath, UK that offer reduced-price food. Users can add places with a map picker, and each place has an expandable section with its location, description, reviews, and ratings.

## Features
- Add places with name, description, and map location (centered on Bath)
- Accordion of places; expanding shows a Leaflet map and details
- Add text reviews and 1-5 star ratings; average rating is calculated
- SQLite database, no migrations required
- Seed route to add two demo places

## Quickstart

1. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the app

```bash
export FLASK_APP=app.py
export FLASK_ENV=development
python app.py
```

3. Open http://127.0.0.1:5000 in your browser.

Optional: Visit `/seed` to populate demo places.

## Notes
- Maps use Leaflet with OpenStreetMap tiles. Requires internet access to load tiles.
- This is a basic prototype. For production, consider adding auth, validation, CSRF protection, and proper migrations.
- Coordinates default to Bath city center if not set.
