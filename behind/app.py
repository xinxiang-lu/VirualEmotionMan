from __future__ import annotations

from importlib import import_module
from pathlib import Path
from time import perf_counter

import click
from flask import Flask, g, request
from sqlalchemy import inspect, text

if __package__ in (None, ""):
    import sys

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

from behind.config import get_config
from behind.extensions import cors, db, migrate, socketio
from behind import models  # noqa: F401  # Ensure model metadata is registered.
from behind.routes import register_blueprints
from behind.services.ai import FaissRAGContextProvider, GLMService, NoopRAGContextProvider
from behind.services.demo_data import clear_demo_data, seed_demo_data
from behind.services.digital_human_identity_service import DigitalHumanIdentityService
from behind.services.multimodal_service import MultimodalService
from behind.services.runtime_metrics import RuntimeMetrics
from behind.utils.realtime import register_socketio_handlers


def ensure_runtime_schema() -> None:
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if "user_settings" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("user_settings")}
    if "voice_speed" not in columns:
        db.session.execute(text("ALTER TABLE user_settings ADD COLUMN voice_speed FLOAT DEFAULT 1.0"))

    if "questionnaire_sessions" in table_names:
        columns = {column["name"] for column in inspector.get_columns("questionnaire_sessions")}
        session_columns = {
            "scale_id": "VARCHAR(64) DEFAULT ''",
            "scale_name": "VARCHAR(120) DEFAULT ''",
            "required_item_count": "INTEGER DEFAULT 0",
            "answered_item_count": "INTEGER DEFAULT 0",
            "total_score": "INTEGER",
            "risk_level": "VARCHAR(20)",
            "summary_json": "JSON",
            "completed_at": "DATETIME",
        }
        for column_name, definition in session_columns.items():
            if column_name not in columns:
                db.session.execute(text(f"ALTER TABLE questionnaire_sessions ADD COLUMN {column_name} {definition}"))

    if "questionnaire_answers" in table_names:
        columns = {column["name"] for column in inspector.get_columns("questionnaire_answers")}
        answer_columns = {
            "session_id": "INTEGER",
            "scale_id": "VARCHAR(64) DEFAULT ''",
        }
        for column_name, definition in answer_columns.items():
            if column_name not in columns:
                db.session.execute(text(f"ALTER TABLE questionnaire_answers ADD COLUMN {column_name} {definition}"))

    if "questionnaire_scores" in table_names:
        columns = {column["name"] for column in inspector.get_columns("questionnaire_scores")}
        score_columns = {
            "session_id": "INTEGER",
            "scale_id": "VARCHAR(64) DEFAULT ''",
            "scale_name": "VARCHAR(120) DEFAULT ''",
        }
        for column_name, definition in score_columns.items():
            if column_name not in columns:
                db.session.execute(text(f"ALTER TABLE questionnaire_scores ADD COLUMN {column_name} {definition}"))

    db.session.commit()


def register_optional_tts_service(app: Flask) -> None:
    capability = {
        "available": False,
        "backend": app.config.get("TTS_BACKEND", ""),
        "reason": "",
    }

    try:
        module = import_module("behind.services.speech.tts_service")
        tts_service_cls = getattr(module, "TtsService")
    except Exception as error:
        capability["reason"] = f"{type(error).__name__}: {error}"
        app.logger.warning("TTS service unavailable, continuing without voice output: %s", error)
        app.extensions["service_capabilities"]["tts"] = capability
        return
        

    try:
        app.extensions["tts_service"] = tts_service_cls(app.config)
        capability["available"] = True
    except Exception as error:
        capability["reason"] = f"{type(error).__name__}: {error}"
        app.logger.warning("TTS service failed to initialize, continuing without voice output: %s", error)

    app.extensions["service_capabilities"]["tts"] = capability


def register_optional_oss_capability(app: Flask) -> None:
    capability = {
        "available": False,
        "configured": False,
        "reason": "",
    }

    config = app.config
    capability["configured"] = all(
        [
            config.get("OSS_ACCESS_KEY_ID"),
            config.get("OSS_ACCESS_KEY_SECRET"),
            config.get("OSS_BUCKET_NAME"),
            config.get("OSS_ENDPOINT"),
        ]
    )

    try:
        import_module("oss2")
    except Exception as error:
        capability["reason"] = f"{type(error).__name__}: {error}"
        app.logger.warning("OSS SDK unavailable, continuing without avatar upload: %s", error)
    else:
        capability["available"] = capability["configured"]
        if not capability["configured"]:
            capability["reason"] = "missing config"

    app.extensions["service_capabilities"]["oss"] = capability


def register_optional_rag_provider(app: Flask) -> None:
    capability = {
        "available": False,
        "backend": "faiss",
        "chunk_count": 0,
        "index_dir": app.config.get("RAG_INDEX_DIR", ""),
        "reason": "",
    }

    provider = FaissRAGContextProvider(app.config)
    if provider.initialize():
        app.extensions["rag_context_provider"] = provider
        capability["available"] = True
        capability["chunk_count"] = provider.status.chunk_count
        capability["index_dir"] = provider.status.index_dir
    else:
        capability["reason"] = provider.status.reason
        app.extensions["rag_context_provider"] = NoopRAGContextProvider()
        if provider.status.reason:
            app.logger.warning("RAG provider unavailable, continuing without retrieval: %s", provider.status.reason)

    app.extensions["service_capabilities"]["rag"] = capability


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    # Ensure SQLite target directory exists before first DB init.
    db_path = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_path.startswith("sqlite:///"):
        sqlite_file = Path(db_path.removeprefix("sqlite:///"))
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    app.extensions["service_capabilities"] = {}
    app.extensions["runtime_metrics"] = RuntimeMetrics()
    app.extensions["rag_context_provider"] = NoopRAGContextProvider()
    GLMService(app).init_app(app)
    DigitalHumanIdentityService(app).init_app(app)
    MultimodalService(app).init_app(app)
    register_optional_rag_provider(app)
    register_optional_tts_service(app)
    register_optional_oss_capability(app)
    with app.app_context():
        db.create_all()
        ensure_runtime_schema()

    register_blueprints(app)
    register_socketio_handlers()
    register_request_metrics(app)
    register_cli(app)
    return app


def register_request_metrics(app: Flask) -> None:
    @app.before_request
    def _start_request_timer() -> None:
        g._request_started_at = perf_counter()

    @app.after_request
    def _record_request_metrics(response):
        started_at = getattr(g, "_request_started_at", None)
        if started_at is not None:
            duration_ms = (perf_counter() - started_at) * 1000
            app.extensions["runtime_metrics"].record_request(
                path=request.path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        return response


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create all database tables."""
        with app.app_context():
            db.create_all()
            ensure_runtime_schema()
        click.echo("Database initialized.")

    @app.cli.command("seed-db")
    @click.option("--force", is_flag=True, help="Clear existing data before seeding demo content.")
    def seed_db_command(force: bool) -> None:
        """Seed demo data for local development."""
        with app.app_context():
            db.create_all()
            ensure_runtime_schema()
            result = seed_demo_data(force=force)
        click.echo(result["message"])

    @app.cli.command("reset-db")
    def reset_db_command() -> None:
        """Clear all known business tables."""
        with app.app_context():
            clear_demo_data()
        click.echo("Database cleared.")


app = create_app()


if __name__ == "__main__":
    socketio.run(app, debug=app.config.get("DEBUG", False), use_reloader=False)
