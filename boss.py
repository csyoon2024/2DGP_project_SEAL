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
        "homing": 15,
        "slam_double": 10,
    },
}
BOSS_HOME_X = 450

PATTERNS = {
    "slam": {
        "kind": "front",
        "telegraph": 0.35,
        "duration": 0.15,
        "recovery": 0.40,
        "hitbox_width": 80,
        "hit_times": (0.0,),
        "telegraph_blink": (0.20, 0.15),
        "aim": "player_x",
        "marker": "spot",
        "pose": "slam",
        "shake": (6, 0.12),
    },
    "charge": {
        "kind": "pierce",
        "telegraph": 0.70,
        "duration": 0.40,
        "recovery": 1.00,
        "hitbox_width": 60,
        "hit_times": (0.0,),
        "telegraph_blink": (0.25, 0.20, 0.15, 0.10),
        "aim": "player_x",
        "marker": "column",
        "pose": "charge",
        "shake": (12, 0.25),
    },
    "shockwave": {
        "kind": "wide",
        "telegraph": 1.00,
        "duration": 0.20,
        "recovery": 0.50,
        "hitbox_width": None,
        "hit_times": (0.0,),
        "telegraph_blink": (0.30, 0.25, 0.20, 0.15, 0.10),
        "aim": "player_lane",
        "marker": "lane",
        "pose": "shockwave",
        "shake": (10, 0.20),
    },
    "homing": {
        "kind": "homing",
        "telegraph": 0.80,
        "duration": 0.30,
        "recovery": 0.40,
        "hitbox_width": 50,
        "hit_times": (0.30,),
        "telegraph_blink": (0.30, 0.20, 0.15, 0.15),
        "aim": "track",
        "marker": "spot",
        "pose": "homing",
        "shake": (6, 0.10),
    },
    "slam_double": {
        "kind": "front",
        "telegraph": 0.35,
        "duration": 0.45,
        "recovery": 0.50,
        "hitbox_width": 80,
        "hit_times": (0.0, 0.30),
        "telegraph_blink": (0.20, 0.15),
        "aim": "player_x",
        "marker": "two_spots",
        "pose": "slam_double",
        "shake": (8, 0.12),
    },
}


@dataclass(frozen=True)
class BossAttack:
    pattern: str
    kind: str
    target_lane: str | None
    target_x: float | None
    hitbox_width: float | None
    hit_index: int = 0


class BossController:
    PATTERN_GAP = 0.60
    AWAKENING_DEMO_DURATION = 2.0
    AWAKENING_SIZE_SCALE = 1.4
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
        self.telegraph_elapsed = 0.0
        self.secondary_target_x = None
        self.forward_progress = 0.0
        self.position_x = BOSS_HOME_X
        self.charge_target_x = BOSS_HOME_X

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
            if self.previous_pattern == "charge":
                self.forward_progress = max(
                    0.0,
                    self.forward_progress - fixed_delta / self.PATTERN_GAP,
                )
                self.position_x = self.charge_target_x + (
                    BOSS_HOME_X - self.charge_target_x
                ) * (1.0 - self.forward_progress)
            if self.timer <= 1e-9:
                self._begin_pattern(phase, player_lane, player_x, rng, forced_pattern)
            return attacks

        if self.state == "telegraph":
            self.timer -= fixed_delta
            self.telegraph_elapsed += fixed_delta
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
            if self.current_pattern == "homing":
                self.target_lane = player_lane
                self.target_x = player_x
            elif self.current_pattern == "charge":
                duration = PATTERNS["charge"]["duration"]
                self.forward_progress = min(self.attack_elapsed / duration, 1.0)
                self.position_x = BOSS_HOME_X + (
                    self.charge_target_x - BOSS_HOME_X
                ) * self.forward_progress
            attacks.extend(self._collect_attacks(self.attack_elapsed))
            if self.timer <= 1e-9:
                self.state = "recovery"
                self.timer = PATTERNS[self.current_pattern]["recovery"]
                if self.current_pattern == "charge":
                    self.forward_progress = 1.0
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
        self.target_x = None
        self.secondary_target_x = None
        if pattern in ("slam", "slam_double"):
            self.target_x = player_x
            self.target_lane = "platform_1"
        elif pattern == "charge":
            self.target_x = player_x
            self.charge_target_x = player_x
            self.target_lane = None
        elif pattern == "shockwave":
            self.target_lane = player_lane
        elif pattern == "homing":
            self.target_lane = player_lane
            self.target_x = player_x
        else:
            self.target_lane = None
        if pattern == "slam_double":
            second_direction = rng.choice((-1, 1))
            if not 0 <= player_x + second_direction * 180 <= 900:
                second_direction *= -1
            self.secondary_target_x = player_x + second_direction * 180
        self.state = "telegraph"
        self.timer = PATTERNS[pattern]["telegraph"]
        self.telegraph_elapsed = 0.0

    def telegraph_is_visible(self):
        if self.state != "telegraph" or self.current_pattern is None:
            return False

        intervals = PATTERNS[self.current_pattern]["telegraph_blink"]
        elapsed = min(self.telegraph_elapsed, sum(intervals))
        for interval_index, interval_duration in enumerate(intervals):
            if elapsed < interval_duration:
                return interval_index == len(intervals) - 1 or interval_index % 2 == 1
            elapsed -= interval_duration
        return True

    def _collect_attacks(self, elapsed):
        pattern = PATTERNS[self.current_pattern]
        attacks = []
        hit_times = pattern["hit_times"]
        while (
            self.next_hit_index < len(hit_times)
            and elapsed + 1e-9 >= hit_times[self.next_hit_index]
        ):
            target_x = self.target_x
            target_lane = self.target_lane
            if self.current_pattern == "slam_double" and self.next_hit_index == 1:
                target_x = self.secondary_target_x
                target_lane = "platform_1"
            attacks.append(
                BossAttack(
                    pattern=self.current_pattern,
                    kind=pattern["kind"],
                    target_lane=target_lane,
                    target_x=target_x,
                    hitbox_width=pattern["hitbox_width"],
                    hit_index=self.next_hit_index,
                )
            )
            self.next_hit_index += 1
        return attacks