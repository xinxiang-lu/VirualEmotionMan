from flask import Flask

from .admin import admin_bp
from .assessment import assessment_bp
from .auth import auth_bp
from .chat import chat_bp
from .health import health_bp
from .user import user_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(assessment_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
