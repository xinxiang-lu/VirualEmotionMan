from __future__ import annotations

VOICE_SPEED_DEFAULT = 1.0
VOICE_SPEED_MIN = 0.8
VOICE_SPEED_MAX = 1.2
VOICE_SPEED_STEP = 0.05
VOICE_SPEED_EFFECTIVE_MIN = 0.6
VOICE_SPEED_EFFECTIVE_MAX = 1.4


def normalize_voice_speed(value, fallback: float = VOICE_SPEED_DEFAULT) -> float:
    target = fallback if value in (None, "") else value
    try:
        numeric = float(target)
    except (TypeError, ValueError) as error:
        raise ValueError("语速格式不正确") from error

    clamped = min(VOICE_SPEED_MAX, max(VOICE_SPEED_MIN, numeric))
    snapped = round(clamped / VOICE_SPEED_STEP) * VOICE_SPEED_STEP
    return round(snapped, 2)


def resolve_effective_voice_speed(value, fallback: float = VOICE_SPEED_DEFAULT) -> float:
    normalized = normalize_voice_speed(value, fallback=fallback)
    if normalized == VOICE_SPEED_DEFAULT:
        return VOICE_SPEED_DEFAULT

    if normalized < VOICE_SPEED_DEFAULT:
        ratio = (VOICE_SPEED_DEFAULT - normalized) / (VOICE_SPEED_DEFAULT - VOICE_SPEED_MIN)
        effective = VOICE_SPEED_DEFAULT - ratio * (VOICE_SPEED_DEFAULT - VOICE_SPEED_EFFECTIVE_MIN)
    else:
        ratio = (normalized - VOICE_SPEED_DEFAULT) / (VOICE_SPEED_MAX - VOICE_SPEED_DEFAULT)
        effective = VOICE_SPEED_DEFAULT + ratio * (VOICE_SPEED_EFFECTIVE_MAX - VOICE_SPEED_DEFAULT)

    return round(effective, 2)
