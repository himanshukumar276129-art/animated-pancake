from dotenv import load_dotenv
from flask import Flask

from config import Config

from .extensions import bcrypt, cors, db, jwt, limiter
from .routes.api import api_bp
from .routes.pages import pages_bp
from .utils import ensure_schema_compatibility, purge_legacy_demo_user


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})
    limiter.init_app(app)

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()
        ensure_schema_compatibility()
        purge_legacy_demo_user()

    return app
