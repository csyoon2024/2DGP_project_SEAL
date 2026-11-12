from dataclasses import dataclass


PHASE_PATTERNS = {
    1: {
        "slam": 50,
        "charge": 20,
        "shockwave": 30,
    },
    2: {
        "slam": 35,
        "charge": 20,
        "shockwave": 20,
        "missile": 15,
        "double_slam": 10,
    },
}

PATTERNS = {
    "slam": {
        "kind": "front",
        "telegraph": 0.35,
        "duration": 0.15,
        "recovery": 0.40,
        "hitbox_width": 80,
        "hit_times": (0.0,),
    },
    "charge": {
        "kind": "piercing",
        "telegraph": 0.70,
        "duration": 0.40,
        "recovery": 1.00,
        "hitbox_width": 60,
        "hit_times": (0.0,),
    },
    "shockwave": {
        "kind": "lane",
        "telegraph": 1.00,
        "duration": 0.20,
        "recovery": 0.50,
        "hitbox_width": None,
        "hit_times": (0.0,),
    },
    "missile": {
        "kind": "tracking",
        "telegraph": 0.80,
        "duration": 0.30,
        "recovery": 0.40,
        "hitbox_width": 50,
        "hit_times": (0.0,),
    },
    "double_slam": {
        "kind": "front",
        "telegraph": 0.35,
        "duration": 0.45,
        "recovery": 0.50,
        "hitbox_width": 80,
        "hit_times": (0.0, 0.225),
    },
}


@dataclass(frozen=True)
class BossAttack:
    pattern: str
    kind: str
    target_lane: str | None
    target_x: float | None
    hitbox_width: float | None


class BossController:
    PATTERN_GAP = 0.60
    AWAKENING_DEMO_DURATION = 2.0
    AWAKENING_SIZE_SCALE = 1.6
    AWAKENING_HITBOX_SCALE = 1.4

    def __init__(self):
        self.awakened = False
        self.phase = 1
        self.reset_for_phase(1)

    def reset_for_phase(self, phase):
        self.state = "rest"
        self.timer = self.PATTERN_GAP
        self.phase = phase
        self.current_pattern = None
        self.previous_pattern = None
        self.target_lane = None
        self.target_x = None
        self.attack_elapsed = 0.0
        self.next_hit_index = 0

    def begin_awakening_demo(self):
        self.awakened = True
        self.state = "awakening"
        self.timer = self.AWAKENING_DEMO_DURATION

    def set_awakened(self, awakened):
        if self.state != "awakening":
            self.awakened = awakened

    def update(self, fixed_delta, phase, player_lane, player_x, rng, forced_pattern=None):
        self.phase = phase
        attacks = []

        if self.state == "awakening":
            self.timer -= fixed_delta
            if self.timer <= 1e-9:
                self.awakened = False
                self.state = "rest"
                self.timer = self.PATTERN_GAP
            return attacks

        if self.state == "rest":
            self.timer -= fixed_delta
            if self.timer <= 1e-9:
                self._begin_pattern(phase, player_lane, player_x, rng, forced_pattern)
            return attacks

        if self.state == "telegraph":
            self.timer -= fixed_delta
            if self.timer <= 1e-9:
                self.state = "active"
                self.timer = PATTERNS[self.current_pattern]["duration"]
                self.attack_elapsed = 0.0
                self.next_hit_index = 0
                attacks.extend(self._collect_attacks(0.0))
            return attacks

        if self.state == "active":
            self.timer -= fixed_delta
            self.attack_elapsed += fixed_delta
            attacks.extend(self._collect_attacks(self.attack_elapsed))
            if self.timer <= 1e-9:
                self.state = "recovery"
                self.timer = PATTERNS[self.current_pattern]["recovery"]
            return attacks

        self.timer -= fixed_delta
        if self.timer <= 1e-9:
            self.state = "rest"
            self.timer = self.PATTERN_GAP
            self.previous_pattern = self.current_pattern
            self.current_pattern = None
            self.target_lane = None
            self.target_x = None
        return attacks

    def _begin_pattern(self, phase, player_lane, player_x, rng, forced_pattern):
        weights = PHASE_PATTERNS[phase]
        if forced_pattern in weights:
            pattern = forced_pattern
        else:
            candidates = [
                name
                for name in weights
                if name != self.previous_pattern and weights[name] > 0
            ]
            if not candidates:
                candidates = list(weights)
            pattern = rng.choices(
                candidates,
                weights=[weights[name] for name in candidates],
                k=1,
            )[0]

        self.current_pattern = pattern
        self.target_x = player_x if pattern == "missile" else None
        if pattern in ("slam", "double_slam"):
            self.target_lane = "platform_1"
        elif pattern == "shockwave":
            self.target_lane = rng.choice(("platform_1", "platform_2"))
        elif pattern == "missile":
            self.target_lane = player_lane
        else:
            self.target_lane = None
        self.state = "telegraph"
        self.timer = PATTERNS[pattern]["telegraph"]

    def _collect_attacks(self, elapsed):
        pattern = PATTERNS[self.current_pattern]
        attacks = []
        hit_times = pattern["hit_times"]
        while (
            self.next_hit_index < len(hit_times)
            and elapsed + 1e-9 >= hit_times[self.next_hit_index]
        ):
            attacks.append(
                BossAttack(
                    pattern=self.current_pattern,
                    kind=pattern["kind"],
                    target_lane=self.target_lane,
                    target_x=self.target_x,
                    hitbox_width=pattern["hitbox_width"],
                )
            )
            self.next_hit_index += 1
        return attacks