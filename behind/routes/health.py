from flask import Blueprint, jsonify


health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.get("/health")
def health_check():
    from flask import current_app

    glm_service = current_app.extensions.get("glm_service")
    glm_status = glm_service.status() if glm_service else None
    multimodal_service = current_app.extensions.get("multimodal_service")
    capabilities = dict(current_app.extensions.get("service_capabilities") or {})
    if multimodal_service is not None:
        capabilities.update(multimodal_service.capability_status())
    return jsonify(
        {
            "status": "ok",
            "service": "behind",
            "llm": {
                "provider": current_app.config.get("LLM_PROVIDER"),
                "configured": glm_status.configured if glm_status else False,
                "sdk_available": glm_status.sdk_available if glm_status else False,
                "model": glm_status.model if glm_status else "",
                "request_count": glm_status.request_count if glm_status else 0,
                "error_count": glm_status.error_count if glm_status else 0,
            },
            "capabilities": capabilities,
        }
    )
