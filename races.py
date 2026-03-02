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


def _clamp_stat(value: float, min_v: int = 60, max_v: int = 130) -> int:
    return max(min_v, min(max_v, int(round(value))))


def _name_variation(name: str) -> float:
    if not name:
        return 0.0
    total = sum(ord(ch) for ch in name)
    normalized = ((total % 13) - 6) / 100.0
    return normalized


def build_car_stats(car_name: str, rarity: str) -> dict:
    base = BASE_STATS_BY_RARITY.get(rarity, BASE_STATS_BY_RARITY["Common"]).copy()
    delta = _name_variation(car_name)
    base["speed"] = _clamp_stat(base["speed"] * (1.0 + delta))
    base["accel"] = _clamp_stat(base["accel"] * (1.0 + (delta * 0.8)))
    base["grip"] = _clamp_stat(base["grip"] * (1.0 - (delta * 0.6)))
    base["reliability"] = _clamp_stat(base["reliability"] * (1.0 + (delta * 0.4)))
    return base


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
    return (
        0.55 * stats["speed"]
        + 0.25 * stats["accel"]
        + 0.12 * stats["grip"]
        + 0.08 * stats["reliability"]
    )


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


def render_progress_line(label: str, icon: str, progress: float, width: int = 16) -> str:
    safe_width = max(10, int(width))
    p = max(0.0, min(100.0, float(progress)))
    pos = int(round((p / 100.0) * (safe_width - 1)))
    cells = ["·"] * safe_width
    cells[pos] = icon
    return f"{label}: {''.join(cells)} {int(round(p))}%"


def render_race_frame(
    player_car_name: str,
    opponent_name: str,
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

    return (
        "🏁 <b>Гонка</b>\n"
        f"Класс: <b>{race_class}</b> | Тик {tick}/{ticks_total}\n\n"
        f"🚘 <b>{player_car_name}</b>\n"
        f"{render_progress_line('Ты', '🏎️', player_progress)}\n\n"
        f"🤖 <b>{opponent_name}</b>\n"
        f"{render_progress_line('Бот', '🚗', opponent_progress)}\n\n"
        f"📣 {status}"
    )


def simulate_race(player_stats: dict, opponent_stats: dict, ticks_total: int = 9) -> dict:
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

    return {
        "frames": frames,
        "winner": winner,
        "player_progress": p,
        "opponent_progress": o,
    }
