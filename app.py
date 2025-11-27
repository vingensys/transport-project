import os
from datetime import datetime

from flask import Flask
from flask_migrate import Migrate

from transport.models import db
from transport.routes.admin import admin_bp


def create_app():
    app = Flask(__name__)

    # Basic config
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "change-me-in-production"

    # Init extensions
    db.init_app(app)
    Migrate(app, db)

    # Blueprints
    app.register_blueprint(admin_bp)

    # Simple test route
    @app.route("/test")
    def test():
        return f"App is working - {datetime.utcnow()}"

    return app


# This is what Flask CLI & `python app.py` will use
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
