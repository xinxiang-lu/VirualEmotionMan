from __future__ import annotations

import mimetypes
from pathlib import Path

from flask import current_app


class DigitalHumanIdentityService:
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    MODEL_REGISTRY = {
        "haru": {
            "label": "Haru",
            "directory": "Haru",
            "model_file": "Haru.model3.json",
        },
        "hiyori": {
            "label": "Hiyori Momose",
            "directory": "Hiyori",
            "model_file": "hiyori_free_t08.model3.json",
        },
    }

    def __init__(self, app=None) -> None:
        self.app = app

    def init_app(self, app) -> None:
        self.app = app
        app.extensions["digital_human_identity_service"] = self

    def list_identities(self) -> list[dict]:
        root = self._root()
        identities = []

        for code, item in self.MODEL_REGISTRY.items():
            directory = root / item["directory"]
            model_path = directory / item["model_file"]
            if not model_path.exists():
                continue

            preview_path = self._find_preview_in_dir(directory)
            identity = {
                "code": code,
                "label": item["label"],
                "directory": item["directory"],
                "model_path": str(model_path.resolve()),
                "model_url": f"/live2d/{item['directory']}/{item['model_file']}",
                "portrait_path": str(preview_path.resolve()) if preview_path else "",
                "portrait_url": (
                    f"/api/users/digital-human-identities/{code}/portrait" if preview_path else ""
                ),
            }
            identities.append(identity)

        return identities

    def get_identity(self, code: str | None) -> dict | None:
        if not code:
            return None
        normalized = str(code).strip().lower()
        for item in self.list_identities():
            if item["code"] == normalized:
                return item
        return None

    def get_selected_identity(self, code: str | None) -> dict | None:
        identities = self.list_identities()
        if not identities:
            return None
        if code:
            identity = self.get_identity(code)
            if identity is not None:
                return identity
        return identities[0]

    def get_portrait_path(self, code: str) -> Path | None:
        identity = self.get_identity(code)
        if identity is None or not identity.get("portrait_path"):
            return None
        path = Path(identity["portrait_path"])
        return path if path.exists() else None

    def get_portrait_mimetype(self, path: Path) -> str:
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or "application/octet-stream"

    def _find_preview_in_dir(self, directory: Path) -> Path | None:
        if not directory.exists():
            return None

        exact_matches = []
        fallback_matches = []
        for candidate in sorted(directory.rglob("*"), key=lambda path: path.as_posix().lower()):
            if not candidate.is_file():
                continue
            suffix = candidate.suffix.lower()
            if suffix not in self.IMAGE_EXTENSIONS:
                continue
            lower_name = candidate.stem.lower()
            if lower_name == "portrait":
                exact_matches.append(candidate)
            elif lower_name == "texture_00":
                fallback_matches.insert(0, candidate)
            else:
                fallback_matches.append(candidate)

        if exact_matches:
            return exact_matches[0]
        return fallback_matches[0] if fallback_matches else None

    def _root(self) -> Path:
        return Path(current_app.config["LIVE2D_MODEL_ROOT"])
