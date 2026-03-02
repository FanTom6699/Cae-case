import json
import os
import random


RACE_CLASS_BY_RARITY = {
    "Common": "D",
    "Rare": "C",
    "Epic": "B",
    "Legendary": "A",
}

BASE_STATS_BY_RARITY = {
    "Common": {"speed": 84, "accel": 82, "grip": 84, "reliability": 88},
    "Rare": {"speed": 92, "accel": 90, "grip": 90, "reliability": 92},
    "Epic": {"speed": 101, "accel": 99, "grip": 98, "reliability": 96},
    "Legendary": {"speed": 112, "accel": 109, "grip": 106, "reliability": 101},
}

BOT_NAMES_BY_CLASS = {
    "D": ["Городской пилот", "Новичок трека", "Уличный драйвер"],
    "C": ["Асфальт-мастер", "Турбо-гонщик", "Ночной пилот"],
    "B": ["Трековый профи", "Скоростной хищник", "Гран-пилот"],
    "A": ["Легенда трассы", "Король апекса", "Титан скорости"],
}

RACE_PROFILE_FIELDS = ("speed", "accel", "grip", "reliability")
REAL_DRIVETRAINS = ("fwd", "rwd", "awd", "4wd")
RACE_PROFILE_META = {
    "version": 3,
    "note": "Race profiles with real-spec based unique stats and tuning",
}
DEFAULT_TUNE_MAX_BONUS = int(os.getenv("RACE_TUNE_MAX_BONUS", "25"))
MAX_TUNE_LEVEL = int(os.getenv("RACE_MAX_TUNE_LEVEL", "15"))

ARCHETYPE_REAL_BASE = {
    "supercar": {"top_speed_kmh": 315, "zero_100_s": 3.5, "weight_kg": 1480, "power_hp": 620, "reliability_index": 74},
    "sports": {"top_speed_kmh": 265, "zero_100_s": 5.4, "weight_kg": 1460, "power_hp": 360, "reliability_index": 80},
    "suv": {"top_speed_kmh": 220, "zero_100_s": 7.0, "weight_kg": 2050, "power_hp": 300, "reliability_index": 86},
    "pickup": {"top_speed_kmh": 195, "zero_100_s": 8.6, "weight_kg": 2250, "power_hp": 280, "reliability_index": 89},
    "classic": {"top_speed_kmh": 175, "zero_100_s": 10.8, "weight_kg": 1280, "power_hp": 150, "reliability_index": 84},
    "drift": {"top_speed_kmh": 235, "zero_100_s": 6.2, "weight_kg": 1320, "power_hp": 290, "reliability_index": 80},
    "sedan": {"top_speed_kmh": 210, "zero_100_s": 8.0, "weight_kg": 1420, "power_hp": 210, "reliability_index": 88},
}

RARITY_REAL_BONUS = {
    "Common": {"top_speed_kmh": -10, "zero_100_s": +0.9, "power_hp": -35, "weight_kg": -20, "reliability_index": +2},
    "Rare": {"top_speed_kmh": +0, "zero_100_s": +0.2, "power_hp": +0, "weight_kg": +0, "reliability_index": +0},
    "Epic": {"top_speed_kmh": +10, "zero_100_s": -0.4, "power_hp": +45, "weight_kg": +20, "reliability_index": -1},
    "Legendary": {"top_speed_kmh": +18, "zero_100_s": -0.8, "power_hp": +90, "weight_kg": +40, "reliability_index": -3},
}

ARCHETYPE_REAL_LIMITS = {
    "supercar": {"top_speed_kmh": (240, 470), "zero_100_s": (1.8, 6.2), "power_hp": (320, 1900), "weight_kg": (980, 2100)},
    "sports": {"top_speed_kmh": (190, 350), "zero_100_s": (3.2, 9.5), "power_hp": (160, 900), "weight_kg": (980, 2100)},
    "suv": {"top_speed_kmh": (150, 310), "zero_100_s": (4.0, 13.5), "power_hp": (140, 820), "weight_kg": (1350, 3400)},
    "pickup": {"top_speed_kmh": (140, 260), "zero_100_s": (4.8, 15.0), "power_hp": (120, 780), "weight_kg": (1450, 3400)},
    "classic": {"top_speed_kmh": (120, 245), "zero_100_s": (5.2, 18.0), "power_hp": (60, 520), "weight_kg": (780, 2200)},
    "drift": {"top_speed_kmh": (170, 320), "zero_100_s": (3.8, 11.5), "power_hp": (140, 800), "weight_kg": (900, 2300)},
    "sedan": {"top_speed_kmh": (140, 300), "zero_100_s": (4.5, 13.5), "power_hp": (90, 720), "weight_kg": (900, 2800)},
}

ARCHETYPE_REAL_DELTA = {
    "supercar": {"top_speed_kmh": +28, "zero_100_s": -0.6, "weight_kg": -40, "power_hp": +90, "reliability_index": -5},
    "sports": {"top_speed_kmh": +16, "zero_100_s": -0.45, "weight_kg": -35, "power_hp": +55, "reliability_index": -2},
    "suv": {"top_speed_kmh": -10, "zero_100_s": +0.7, "weight_kg": +280, "power_hp": +25, "reliability_index": +4},
    "pickup": {"top_speed_kmh": -14, "zero_100_s": +0.9, "weight_kg": +360, "power_hp": +35, "reliability_index": +6},
    "classic": {"top_speed_kmh": -22, "zero_100_s": +1.3, "weight_kg": -40, "power_hp": -15, "reliability_index": +2},
    "drift": {"top_speed_kmh": +8, "zero_100_s": -0.3, "weight_kg": -55, "power_hp": +35, "reliability_index": -1},
    "sedan": {"top_speed_kmh": 0, "zero_100_s": 0.0, "weight_kg": 0, "power_hp": 0, "reliability_index": 0},
}

CLASS_TARGET_POWER = {
    "Common": 84.0,
    "Rare": 92.0,
    "Epic": 101.0,
    "Legendary": 110.0,
}

CLASS_POWER_TOLERANCE = 8.0
CLASS_POWER_TOLERANCE_TUNED = float(os.getenv("RACE_CLASS_POWER_TOLERANCE_TUNED", "10"))

TUNING_PRICE_BY_CLASS = {
    "D": {
        "base": int(os.getenv("RACE_TUNE_D_BASE", "3000")),
        "step": int(os.getenv("RACE_TUNE_D_STEP", "1500")),
    },
    "C": {
        "base": int(os.getenv("RACE_TUNE_C_BASE", "5000")),
        "step": int(os.getenv("RACE_TUNE_C_STEP", "2500")),
    },
    "B": {
        "base": int(os.getenv("RACE_TUNE_B_BASE", "8000")),
        "step": int(os.getenv("RACE_TUNE_B_STEP", "4000")),
    },
    "A": {
        "base": int(os.getenv("RACE_TUNE_A_BASE", "12000")),
        "step": int(os.getenv("RACE_TUNE_A_STEP", "6000")),
    },
}

TUNING_ARCHETYPE_MULTIPLIER = {
    "classic": float(os.getenv("RACE_TUNE_MULT_CLASSIC", "0.80")),
    "sedan": float(os.getenv("RACE_TUNE_MULT_SEDAN", "0.90")),
    "pickup": float(os.getenv("RACE_TUNE_MULT_PICKUP", "1.00")),
    "suv": float(os.getenv("RACE_TUNE_MULT_SUV", "1.08")),
    "drift": float(os.getenv("RACE_TUNE_MULT_DRIFT", "1.10")),
    "sports": float(os.getenv("RACE_TUNE_MULT_SPORTS", "1.18")),
    "supercar": float(os.getenv("RACE_TUNE_MULT_SUPERCAR", "1.28")),
}

ARCHETYPE_BY_KEYWORD = {
    "supercar": [
        "ferrari", "lamborghini", "mclaren", "bugatti", "koenigsegg", "pagani", "porsche_911", "aventador", "huracan", "svj",
    ],
    "sports": [
        "supra", "gtr", "skyline", "m3", "m4", "m5", "rs", "amg", "corvette", "mustang", "camaro", "charger", "challenger",
    ],
    "suv": [
        "land_cruiser", "prado", "patrol", "g_class", "gelandewagen", "range_rover", "q7", "x5", "x7", "gle", "gls", "cayenne", "touareg", "defender", "wrangler",
    ],
    "pickup": [
        "pickup", "raptor", "hilux", "navara", "tundra", "ram", "f150", "silverado",
    ],
    "classic": [
        "2101", "2106", "2107", "412", "volga", "mustang_196", "camaro_196", "chevelle", "beetle", "mini_classic", "e30", "w123",
    ],
    "drift": [
        "silvia", "ae86", "rx7", "rx_7", "240sx", "chaser", "mark_ii",
    ],
}

ARCHETYPE_DELTA = {
    "supercar": {"speed": +10, "accel": +8, "grip": +2, "reliability": -4},
    "sports": {"speed": +6, "accel": +5, "grip": +2, "reliability": -1},
    "suv": {"speed": +1, "accel": 0, "grip": +5, "reliability": +6},
    "pickup": {"speed": -3, "accel": -2, "grip": +4, "reliability": +8},
    "classic": {"speed": -4, "accel": -5, "grip": +1, "reliability": +3},
    "drift": {"speed": +3, "accel": +3, "grip": +7, "reliability": -2},
    "sedan": {"speed": 0, "accel": 0, "grip": +1, "reliability": +2},
}


def _clamp_stat(value: float, min_v: int = 60, max_v: int = 130) -> int:
    return max(min_v, min(max_v, int(round(value))))


def _clamp_float(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, float(value)))


def _stats_power(stats: dict) -> float:
    return (
        0.55 * float(stats.get("speed", 0))
        + 0.25 * float(stats.get("accel", 0))
        + 0.12 * float(stats.get("grip", 0))
        + 0.08 * float(stats.get("reliability", 0))
    )


def _safe_float(value, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _name_variation(name: str) -> float:
    if not name:
        return 0.0
    total = sum(ord(ch) for ch in name)
    normalized = ((total % 13) - 6) / 100.0
    return normalized


def _default_car_stats(car_name: str, rarity: str) -> dict:
    base = BASE_STATS_BY_RARITY.get(rarity, BASE_STATS_BY_RARITY["Common"]).copy()
    delta = _name_variation(car_name)
    base["speed"] = _clamp_stat(base["speed"] * (1.0 + delta))
    base["accel"] = _clamp_stat(base["accel"] * (1.0 + (delta * 0.8)))
    base["grip"] = _clamp_stat(base["grip"] * (1.0 - (delta * 0.6)))
    base["reliability"] = _clamp_stat(base["reliability"] * (1.0 + (delta * 0.4)))
    return base


def _default_drivetrain(archetype: str) -> str:
    if archetype in {"supercar", "sports", "drift"}:
        return "rwd"
    if archetype == "suv":
        return "awd"
    if archetype == "pickup":
        return "4wd"
    return "fwd"


def _infer_real_specs(car_name: str, rarity: str, archetype: str) -> dict:
    base = dict(ARCHETYPE_REAL_BASE.get(archetype, ARCHETYPE_REAL_BASE["sedan"]))
    bonus = dict(RARITY_REAL_BONUS.get(rarity, RARITY_REAL_BONUS["Common"]))
    delta = ARCHETYPE_REAL_DELTA.get(archetype, ARCHETYPE_REAL_DELTA["sedan"])
    limits = ARCHETYPE_REAL_LIMITS.get(archetype, ARCHETYPE_REAL_LIMITS["sedan"])
    var = _name_variation(car_name)

    top_speed = base["top_speed_kmh"] + bonus["top_speed_kmh"] + delta["top_speed_kmh"] + (var * 30)
    zero_100 = base["zero_100_s"] + bonus["zero_100_s"] + delta["zero_100_s"] - (var * 0.7)
    weight = base["weight_kg"] + bonus["weight_kg"] + delta["weight_kg"] - (var * 90)
    power = base["power_hp"] + bonus["power_hp"] + delta["power_hp"] + (var * 95)
    reliability = base["reliability_index"] + bonus["reliability_index"] + delta["reliability_index"] - (var * 8)

    return {
        "real_top_speed_kmh": int(round(_clamp_float(top_speed, limits["top_speed_kmh"][0], limits["top_speed_kmh"][1]))),
        "real_zero_100_s": round(_clamp_float(zero_100, limits["zero_100_s"][0], limits["zero_100_s"][1]), 2),
        "real_weight_kg": int(round(_clamp_float(weight, limits["weight_kg"][0], limits["weight_kg"][1]))),
        "real_power_hp": int(round(_clamp_float(power, limits["power_hp"][0], limits["power_hp"][1]))),
        "real_reliability_index": int(round(_clamp_float(reliability, 50.0, 99.0))),
        "real_drivetrain": _default_drivetrain(archetype),
    }


def _real_specs_to_stats(real_specs: dict, rarity: str, archetype: str) -> dict:
    top_speed = float(real_specs.get("real_top_speed_kmh", 180))
    zero_100 = float(real_specs.get("real_zero_100_s", 10.0))
    weight_kg = float(real_specs.get("real_weight_kg", 1300))
    power_hp = float(real_specs.get("real_power_hp", 100))
    reliability_index = float(real_specs.get("real_reliability_index", 85))
    drivetrain = str(real_specs.get("real_drivetrain", "fwd")).lower()

    hp_per_ton = power_hp / max(0.8, (weight_kg / 1000.0))
    speed_score = 58.0 + ((top_speed - 120.0) * 0.24)
    accel_score = 56.0 + ((hp_per_ton - 70.0) * 0.12) + ((11.5 - zero_100) * 3.8)

    drivetrain_bonus = {
        "fwd": 0.0,
        "rwd": 2.0,
        "awd": 4.0,
        "4wd": 3.0,
    }.get(drivetrain, 0.0)

    archetype_grip_bonus = {
        "supercar": 2.0,
        "sports": 2.0,
        "drift": 4.0,
        "suv": 2.0,
        "pickup": 1.0,
        "classic": 0.0,
        "sedan": 1.0,
    }.get(archetype, 1.0)

    grip_score = 60.0 + drivetrain_bonus + archetype_grip_bonus + ((1900.0 - weight_kg) / 180.0)
    reliability_score = 45.0 + (reliability_index * 0.58) - max(0.0, (power_hp - 450.0) / 45.0)

    stats = {
        "speed": _clamp_stat(speed_score),
        "accel": _clamp_stat(accel_score),
        "grip": _clamp_stat(grip_score),
        "reliability": _clamp_stat(reliability_score),
    }

    target = CLASS_TARGET_POWER.get(rarity, 90.0)
    current = _stats_power(stats)

    if current > (target + CLASS_POWER_TOLERANCE) or current < (target - CLASS_POWER_TOLERANCE):
        scale = target / max(1.0, current)
        for field in RACE_PROFILE_FIELDS:
            stats[field] = _clamp_stat(stats[field] * scale)

    return stats


def _enforce_class_power_cap(profile: dict, rarity: str, tolerance: float | None = None) -> dict:
    limit_tolerance = float(CLASS_POWER_TOLERANCE_TUNED if tolerance is None else tolerance)
    target = CLASS_TARGET_POWER.get(rarity, CLASS_TARGET_POWER["Common"])
    max_allowed = target + max(1.0, limit_tolerance)

    current_stats = {
        "speed": int(profile.get("speed", profile.get("base_speed", 60))),
        "accel": int(profile.get("accel", profile.get("base_accel", 60))),
        "grip": int(profile.get("grip", profile.get("base_grip", 60))),
        "reliability": int(profile.get("reliability", profile.get("base_reliability", 60))),
    }

    current_power = _stats_power(current_stats)
    if current_power <= max_allowed:
        return profile

    scale = max_allowed / max(1.0, current_power)
    for field in RACE_PROFILE_FIELDS:
        base_key = f"base_{field}"
        base_v = int(profile.get(base_key, current_stats[field]))
        scaled = _clamp_stat(current_stats[field] * scale)
        profile[field] = max(base_v, scaled)

    return profile


def _detect_archetype(car_name: str) -> str:
    key = (car_name or "").lower()
    for archetype, keywords in ARCHETYPE_BY_KEYWORD.items():
        if any(keyword in key for keyword in keywords):
            return archetype
    return "sedan"


def _build_profile_default_entry(car_name: str, rarity: str) -> dict:
    archetype = _detect_archetype(car_name)
    real_specs = _infer_real_specs(car_name, rarity, archetype)
    tuned_base = _real_specs_to_stats(real_specs, rarity, archetype)

    return {
        "class": RACE_CLASS_BY_RARITY.get(rarity, "D"),
        "archetype": archetype,
        **real_specs,
        "base_speed": tuned_base["speed"],
        "base_accel": tuned_base["accel"],
        "base_grip": tuned_base["grip"],
        "base_reliability": tuned_base["reliability"],
        "speed": tuned_base["speed"],
        "accel": tuned_base["accel"],
        "grip": tuned_base["grip"],
        "reliability": tuned_base["reliability"],
        "tune_level": 1,
    }


def _normalize_profile_entry(entry: dict, fallback_entry: dict, rarity: str) -> dict:
    normalized = {
        "class": entry.get("class") or RACE_CLASS_BY_RARITY.get(rarity, "D"),
        "archetype": entry.get("archetype") or fallback_entry.get("archetype", "sedan"),
    }

    normalized_real = {
        "real_top_speed_kmh": int(round(_clamp_float(_safe_float(entry.get("real_top_speed_kmh", fallback_entry["real_top_speed_kmh"]), fallback_entry["real_top_speed_kmh"]), 120.0, 470.0))),
        "real_zero_100_s": round(_clamp_float(_safe_float(entry.get("real_zero_100_s", fallback_entry["real_zero_100_s"]), fallback_entry["real_zero_100_s"]), 1.8, 18.0), 2),
        "real_weight_kg": int(round(_clamp_float(_safe_float(entry.get("real_weight_kg", fallback_entry["real_weight_kg"]), fallback_entry["real_weight_kg"]), 680.0, 3400.0))),
        "real_power_hp": int(round(_clamp_float(_safe_float(entry.get("real_power_hp", fallback_entry["real_power_hp"]), fallback_entry["real_power_hp"]), 45.0, 1900.0))),
        "real_reliability_index": int(round(_clamp_float(_safe_float(entry.get("real_reliability_index", fallback_entry["real_reliability_index"]), fallback_entry["real_reliability_index"]), 50.0, 99.0))),
        "real_drivetrain": str(entry.get("real_drivetrain", fallback_entry["real_drivetrain"]).lower()),
    }
    if normalized_real["real_drivetrain"] not in REAL_DRIVETRAINS:
        normalized_real["real_drivetrain"] = fallback_entry["real_drivetrain"]
    normalized.update(normalized_real)

    computed_base = _real_specs_to_stats(normalized_real, rarity, normalized["archetype"])

    for field in RACE_PROFILE_FIELDS:
        base_key = f"base_{field}"
        normalized[base_key] = computed_base[field]

    for field in RACE_PROFILE_FIELDS:
        raw_value = entry.get(field, fallback_entry[field])
        cap = normalized[f"base_{field}"] + max(1, DEFAULT_TUNE_MAX_BONUS)
        try:
            normalized[field] = _clamp_stat(float(raw_value), min_v=60, max_v=max(130, cap))
        except Exception:
            normalized[field] = fallback_entry[field]

        normalized[field] = max(normalized[f"base_{field}"], min(normalized[field], cap))

    normalized["tune_level"] = max(1, int(entry.get("tune_level", 1)))
    return _enforce_class_power_cap(normalized, rarity)


def _get_profiles_file_path(file_path: str | None = None) -> str:
    return file_path or os.getenv("RACE_PROFILES_PATH", "race_profiles.json")


def _get_maps_file_path(file_path: str | None = None) -> str:
    return file_path or os.getenv("RACE_MAPS_PATH", "race_maps.json")


def _default_race_map() -> dict:
    return {
        "id": "standard_track",
        "name_ru": "Стандартный трек",
        "description_ru": "Сбалансированная конфигурация без специальных бонусов.",
        "modifiers": {
            "speed": 1.0,
            "accel": 1.0,
            "grip": 1.0,
            "reliability": 1.0,
        },
    }


def _normalize_race_map(item: dict) -> dict:
    if not isinstance(item, dict):
        return _default_race_map()

    modifiers_raw = item.get("modifiers", {}) if isinstance(item.get("modifiers"), dict) else {}
    modifiers = {}
    for field in RACE_PROFILE_FIELDS:
        val = _safe_float(modifiers_raw.get(field, 1.0), 1.0)
        modifiers[field] = _clamp_float(val, 0.75, 1.30)

    return {
        "id": str(item.get("id") or "map_unknown"),
        "name_ru": str(item.get("name_ru") or "Трек"),
        "description_ru": str(item.get("description_ru") or "Описание трека отсутствует."),
        "modifiers": modifiers,
    }


def load_race_maps(file_path: str | None = None) -> list[dict]:
    maps_path = _get_maps_file_path(file_path)

    try:
        with open(maps_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return [_default_race_map()]

    if not isinstance(payload, dict):
        return [_default_race_map()]

    maps = payload.get("maps")
    if not isinstance(maps, list):
        return [_default_race_map()]

    normalized = []
    seen_ids = set()
    for item in maps:
        race_map = _normalize_race_map(item)
        if race_map["id"] in seen_ids:
            continue
        seen_ids.add(race_map["id"])
        normalized.append(race_map)

    return normalized or [_default_race_map()]


def pick_random_race_map(race_maps: list[dict] | None = None) -> dict:
    pool = race_maps or [_default_race_map()]
    return random.choice(pool)


def apply_map_modifiers_to_stats(stats: dict, race_map: dict) -> dict:
    base_stats = dict(stats or {})
    modifiers = (race_map or {}).get("modifiers", {}) if isinstance((race_map or {}).get("modifiers", {}), dict) else {}

    result = {}
    for field in RACE_PROFILE_FIELDS:
        value = _safe_float(base_stats.get(field, 60), 60)
        mod = _safe_float(modifiers.get(field, 1.0), 1.0)
        result[field] = _clamp_stat(value * mod)

    return result


def ensure_race_profiles(cards_catalog: dict, file_path: str | None = None) -> dict:
    profile_path = _get_profiles_file_path(file_path)
    file_data = {}
    cars_profiles = {}

    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                if isinstance(loaded.get("cars"), dict):
                    file_data = loaded
                    cars_profiles = dict(loaded.get("cars", {}))
                else:
                    cars_profiles = dict(loaded)
                    file_data = {
                        "meta": dict(RACE_PROFILE_META),
                        "cars": cars_profiles,
                    }
        except Exception:
            file_data = {}
            cars_profiles = {}

    if not file_data:
        file_data = {
            "meta": dict(RACE_PROFILE_META),
            "cars": cars_profiles,
        }
    else:
        file_data["meta"] = dict(RACE_PROFILE_META)

    changed = False
    valid_ids = set(cards_catalog.keys())

    for car_id, card in cards_catalog.items():
        rarity = card.get("rarity", "Common")
        fallback_entry = _build_profile_default_entry(car_id, rarity)

        existing = cars_profiles.get(car_id)
        if not isinstance(existing, dict):
            cars_profiles[car_id] = fallback_entry
            changed = True
            continue

        normalized = _normalize_profile_entry(existing, fallback_entry, rarity)
        if normalized != existing:
            cars_profiles[car_id] = normalized
            changed = True

    stale_ids = [car_id for car_id in cars_profiles if car_id not in valid_ids]
    if stale_ids:
        for car_id in stale_ids:
            del cars_profiles[car_id]
        changed = True

    if changed or not os.path.exists(profile_path):
        save_race_profiles(cars_profiles, file_path=profile_path)

    return cars_profiles


def save_race_profiles(race_profiles: dict, file_path: str | None = None) -> None:
    profile_path = _get_profiles_file_path(file_path)
    payload = {
        "meta": dict(RACE_PROFILE_META),
        "cars": dict(sorted((race_profiles or {}).items(), key=lambda kv: kv[0])),
    }
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def get_car_profile(car_name: str, rarity: str, race_profiles: dict | None = None) -> dict:
    fallback_entry = _build_profile_default_entry(car_name, rarity)
    if not race_profiles:
        return fallback_entry

    profile = race_profiles.get(car_name)
    if not isinstance(profile, dict):
        race_profiles[car_name] = fallback_entry
        return fallback_entry

    normalized = _normalize_profile_entry(profile, fallback_entry, rarity)
    if normalized != profile:
        race_profiles[car_name] = normalized
    return normalized


def get_tuning_cost(profile: dict) -> int:
    level = max(1, int((profile or {}).get("tune_level", 1)))
    class_code = str((profile or {}).get("class", "D")).upper()
    pricing = TUNING_PRICE_BY_CLASS.get(class_code, TUNING_PRICE_BY_CLASS["D"])
    archetype = str((profile or {}).get("archetype", "sedan")).lower()
    archetype_mult = float(TUNING_ARCHETYPE_MULTIPLIER.get(archetype, 1.0))

    base_cost = pricing["base"] + ((level - 1) * pricing["step"])
    return max(1000, int(round(base_cost * archetype_mult)))


def is_tuning_maxed(profile: dict) -> bool:
    level = max(1, int((profile or {}).get("tune_level", 1)))
    return level >= max(1, MAX_TUNE_LEVEL)


def apply_tuning_upgrade(
    car_name: str,
    rarity: str,
    race_profiles: dict,
    stat: str,
    max_bonus: int | None = None,
) -> tuple[bool, dict, str]:
    if stat not in RACE_PROFILE_FIELDS:
        return False, {}, "invalid_stat"

    profile = get_car_profile(car_name, rarity, race_profiles)
    if is_tuning_maxed(profile):
        return False, profile, "max_level_reached"

    bonus_limit = max(1, int(max_bonus if max_bonus is not None else DEFAULT_TUNE_MAX_BONUS))

    base_key = f"base_{stat}"
    current_value = int(profile.get(stat, 0))
    cap = int(profile.get(base_key, current_value)) + bonus_limit
    if current_value >= cap:
        return False, profile, "cap_reached"

    profile[stat] = min(cap, current_value + 1)

    projected_power = _stats_power(profile)
    target = CLASS_TARGET_POWER.get(rarity, CLASS_TARGET_POWER["Common"])
    max_allowed = target + max(1.0, CLASS_POWER_TOLERANCE_TUNED)
    if projected_power > max_allowed:
        profile[stat] = current_value
        return False, profile, "class_power_cap"

    profile["tune_level"] = max(1, int(profile.get("tune_level", 1)) + 1)
    race_profiles[car_name] = profile
    return True, profile, "ok"


def build_car_stats(car_name: str, rarity: str, race_profiles: dict | None = None) -> dict:
    normalized = get_car_profile(car_name, rarity, race_profiles)
    return {
        "speed": normalized["speed"],
        "accel": normalized["accel"],
        "grip": normalized["grip"],
        "reliability": normalized["reliability"],
    }


def make_bot_opponent(player_rarity: str) -> tuple[str, str, dict]:
    race_class = RACE_CLASS_BY_RARITY.get(player_rarity, "D")
    names = BOT_NAMES_BY_CLASS.get(race_class, BOT_NAMES_BY_CLASS["D"])
    bot_name = random.choice(names)

    class_to_rarity = {
        "D": "Common",
        "C": "Rare",
        "B": "Epic",
        "A": "Legendary",
    }
    bot_rarity = class_to_rarity.get(race_class, "Common")
    stats = build_car_stats(bot_name, bot_rarity)
    return bot_name, race_class, stats


def _power(stats: dict) -> float:
    return _stats_power(stats)


def _tick_step(stats: dict, tick: int, ticks_total: int) -> float:
    base_step = 100.0 / max(1, ticks_total)
    perf = _power(stats) / 100.0
    jitter = random.uniform(0.96, 1.04)
    accel_boost = 1.0
    if tick <= 2:
        accel_boost += (stats["accel"] - 95) / 220.0

    grip_penalty = 1.0
    if random.random() < 0.09:
        grip_penalty -= max(0.0, (102 - stats["grip"]) / 180.0)

    reliability_penalty = 1.0
    if random.random() < 0.06:
        reliability_penalty -= max(0.0, (105 - stats["reliability"]) / 220.0)

    step = base_step * perf * jitter * accel_boost * grip_penalty * reliability_penalty
    return max(2.2, step)


def render_progress_line(label: str, icon: str, progress: float, width: int = 12) -> str:
    safe_width = max(8, int(width))
    safe_label = (label or "Игрок").strip()
    if len(safe_label) > 10:
        safe_label = f"{safe_label[:9]}…"

    p = max(0.0, min(100.0, float(progress)))
    pos = int(round((p / 100.0) * (safe_width - 1)))
    cells = ["·"] * safe_width
    cells[pos] = icon
    return f"{safe_label}: {''.join(cells)} {int(round(p))}%"


def render_race_frame(
    player_label: str,
    player_car_name: str,
    opponent_name: str,
    opponent_label: str,
    player_progress: float,
    opponent_progress: float,
    race_class: str,
    tick: int,
    ticks_total: int,
) -> str:
    status = "Ровная борьба"
    diff = player_progress - opponent_progress
    if diff >= 8:
        status = "Ты уверенно впереди"
    elif diff >= 3:
        status = "Ты чуть впереди"
    elif diff <= -8:
        status = "Соперник уходит вперёд"
    elif diff <= -3:
        status = "Соперник немного впереди"

    car_icon = "🚘"

    return (
        "🏁 <b>Гонка</b>\n"
        f"Класс: <b>{race_class}</b> | Тик {tick}/{ticks_total}\n\n"
        f"🚘 <b>{player_car_name}</b>\n"
        f"{render_progress_line(player_label, car_icon, player_progress)}\n\n"
        f"🤖 <b>{opponent_name}</b>\n"
        f"{render_progress_line(opponent_label, car_icon, opponent_progress)}\n\n"
        f"📣 {status}"
    )


def simulate_race(player_stats: dict, opponent_stats: dict, ticks_total: int = 9) -> dict:
    def _estimate_time_from_frames(items: list[dict], key: str, tick_duration_s: float = 1.0) -> float:
        if not items:
            return 0.0

        prev_progress = 0.0
        for index, frame in enumerate(items, start=1):
            current = float(frame.get(key, 0.0))
            if current >= 100.0:
                delta = max(0.0001, current - prev_progress)
                part = (100.0 - prev_progress) / delta
                part = max(0.0, min(1.0, part))
                return ((index - 1) + part) * tick_duration_s
            prev_progress = current

        final_progress = max(1.0, float(items[-1].get(key, 0.0)))
        full_time = len(items) * tick_duration_s
        return full_time * (100.0 / final_progress)

    p = 0.0
    o = 0.0
    frames = []

    for tick in range(1, max(2, ticks_total) + 1):
        p += _tick_step(player_stats, tick, ticks_total)
        o += _tick_step(opponent_stats, tick, ticks_total)

        p = min(100.0, p)
        o = min(100.0, o)
        frames.append({"tick": tick, "player_progress": p, "opponent_progress": o})

        if p >= 100.0 or o >= 100.0:
            break

    winner = "draw"
    if p > o:
        winner = "player"
    elif o > p:
        winner = "opponent"

    player_time_s = _estimate_time_from_frames(frames, "player_progress", tick_duration_s=1.0)
    opponent_time_s = _estimate_time_from_frames(frames, "opponent_progress", tick_duration_s=1.0)

    return {
        "frames": frames,
        "winner": winner,
        "player_progress": p,
        "opponent_progress": o,
        "player_time_s": player_time_s,
        "opponent_time_s": opponent_time_s,
    }
