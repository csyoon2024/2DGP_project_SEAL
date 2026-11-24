from dataclasses import dataclass


PHASE_PATTERNS = {
    # 후려치기(backhand) 추가로 가중치 재배분 — 1페이즈 slam 50 → 40, shockwave 30 → 25,
    # charge 20 → 15 / 2페이즈 slam 35 → 30, charge 20 → 15, homing 15 → 10
    1: {
        "slam": 40,
        "backhand": 20,
        "shockwave": 25,
        "charge": 15,
    },
    2: {
        "slam": 30,
        "backhand": 15,
        "shockwave": 20,
        "charge": 15,
        "homing": 10,
        "slam_double": 10,
    },
}
BOSS_HOME_X = 450

# 페이즈별 수치 차등 — 페이즈로 달라지는 수치는 전부 여기 모은다 (패턴 가중치는 PHASE_PATTERNS).
# 누수 속도(SealGauge.LEAK_PER_SECOND)는 일부러 넣지 않았다: 올리면 순수지가 떨어져
# 페이즈가 길어지고, 2페이즈는 이미 약 40초로 상한이다.
PHASE_MODIFIERS = {
    1: {
        # 예고 1.00 → 1.15: 시전이 너무 빠르다는 플레이 피드백. 내리찍기 0.35 → 0.40,
        #   돌진 0.70 → 0.805, 충격파 1.00 → 1.15. 지속·후경직은 그대로라 패턴 주기만
        #   평균 약 0.09초(≈5%) 길어진다
        "telegraph_scale": 1.15,
        "hit_loss": 0.15,
        "awaken_threshold": 0.85,
    },
    2: {
        # 예고 0.85 → 1.00: 시전이 너무 빠르다는 플레이 피드백으로 1페이즈와 함께 늦췄다.
        #   1페이즈(1.15)보다 15%쯤 빠른 차등은 유지된다. 내리찍기 0.35, 돌진 0.70,
        #   충격파 1.00, 유도탄 0.80 = 차등 도입 전 원래 값이라 전투 길이(약 40초)도 원래대로다
        "telegraph_scale": 1.00,
        # 피격 손실 0.15 → 0.18 (+20%): 2페이즈의 실수 대가를 키운다. 각성 중 손실도 같은 비율
        #   (0.20 → 0.24). 안 맞으면 전투 길이에 영향이 없다
        "hit_loss": 0.18,
        # 각성 진입 0.85 → 0.80: 더 일찍 각성한다. 해제선 0.60과 0.20 간격이 남아 경계에서
        #   깜빡이지 않는다
        "awaken_threshold": 0.80,
    },
}
# 예고 시간 하한(초). 사람 반응 한계가 0.25초 근처라 그 아래로 내려가면 실력이 아니라 운이 된다
MIN_TELEGRAPH = 0.30


def telegraph_duration(pattern, phase):
    """페이즈 배율과 하한을 적용한 예고 시간. 패턴 시작 시 한 번만 계산한다."""
    scale = PHASE_MODIFIERS[phase]["telegraph_scale"]
    return max(MIN_TELEGRAPH, PATTERNS[pattern]["telegraph"] * scale)
# ---------------------------------------------------------------------------
# 부위 파괴. 공격이 적중한 순간 플레이어의 논리 x가 어느 구역인지로 맞은 부위를 정한다.
# 공격 가능 범위는 보스 중심 450 ± 155 = 295~605 (BASIC_ATTACK_REACH 120 + 보스 반폭 35).
# 이름은 화면 기준 (보스 기준 좌우는 헷갈린다). 구역은 겹치지 않고, 295~300 / 600~605처럼
# 구역 밖 끝자락은 가까운 팔로 친다 (part_at).
#   (이름, 왼쪽 x, 오른쪽 x, 내구도 — None이면 파괴 불가)
# 내구도 8: 기본 공격(1) 8회 또는 강공격(3) 3회. 그동안 게이지를 못 미는 대가로 적당한 길이
# ---------------------------------------------------------------------------
BOSS_PARTS = (
    ("arm_l", 300, 400, 8),  # 화면 왼쪽 팔
    ("core", 400, 500, None),  # 핵 — 게이지를 미는 곳
    ("arm_r", 500, 600, 8),  # 화면 오른쪽 팔
)
# 팔에 맞았을 때 깎이는 내구도. 팔에 맞으면 게이지는 밀지 않는다
PART_DAMAGE = {"basic": 1, "heavy": 3}
# 팔을 부순 순간의 일회성 보상: 게이지를 플레이어 쪽으로 이만큼 민다 (기본 4 / 강공격 12와 같은 척도.
#   SealGauge.GAUGE_CHANGE_SCALE이 똑같이 곱해진다)
PART_BREAK_GAUGE_BONUS = 0.10
# 패턴을 쓰는 부위. 팔이 부서지면 그 팔을 쓰는 패턴은 그 전투 동안 나오지 않는다.
#   both_arms: 하나라도 부서지면 사용 불가. body·core: 파괴 불가라 항상 남는다
PATTERN_PART = {
    "slam": "arm_r",
    "backhand": "arm_l",
    "shockwave": "both_arms",
    "slam_double": "both_arms",
    "charge": "body",
    "homing": "core",
}


def part_at(logical_x):
    """논리 x가 속한 부위 이름. 구역 밖 끝자락은 가장 가까운 구역으로."""
    for name, left, right, _ in BOSS_PARTS:
        if left <= logical_x < right:
            return name
    if logical_x < BOSS_PARTS[0][1]:
        return BOSS_PARTS[0][0]
    return BOSS_PARTS[-1][0]


# 내리찍기 충격이 앞줄에 먼저 닿고 뒷줄에는 이만큼 늦게 닿는다 (초).
#   보스에서 가까운 앞줄이 먼저 맞아야 내리찍은 충격이 앞으로 퍼져 나오는 것처럼 읽힌다.
#   0.12: 두 번 터지는 게 눈에 보일 만큼 길고, 내리찍기 실행 시간(0.15)과
#   연속 내리찍기 2타(0.30 + 0.12 = 0.42 < 0.45) 안에 들어갈 만큼 짧다
SLAM_REAR_DELAY = 0.12

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
    # 후려치기 — 왼팔(arm_l)을 수평으로 뻗어 옆에서 쓸어친다. 앞줄 전용. 뒷줄로 물러나야만 피한다.
    #   판정폭 200 → 440: 200은 플레이어 반폭(25)을 더해도 좌우 125까지만 닿아 회피 대시(160)나
    #   예고 중 걷기(0.575초 × 320 ≈ 184)로 빠져나갈 수 있었다. 예고 시작과 동시에 회피 + 이어 걷기가
    #   가장 멀리 가는 방법이고 1페이즈에서 235를 간다 (측정). 440이면 도달 245로 이것도 넘는다.
    #   회피 무적도 이 패턴에는 적용되지 않는다 (ArenaScene.resolve_boss_attack)
    "backhand": {
        "kind": "front",
        "telegraph": 0.50,
        "duration": 0.20,
        "recovery": 0.60,
        "hitbox_width": 440,
        "hit_times": (0.0,),
        "telegraph_blink": (0.25, 0.15, 0.10),
        "aim": "player_x",
        "marker": "sweep",
        "pose": "backhand",
        "shake": (8, 0.14),
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
    # 내리찍기의 뒷줄 시간차 타격이면 True
    delayed: bool = False


class BossController:
    PATTERN_GAP = 0.60
    AWAKENING_DEMO_DURATION = 2.0
    AWAKENING_SIZE_SCALE = 1.4
    AWAKENING_HITBOX_SCALE = 1.4

    def __init__(self):
        self.awakened = False
        self.phase = 1
        self.reset_parts()
        self.reset_for_phase(1)

    # --- 부위 -----------------------------------------------------------------
    def reset_parts(self):
        """부위 내구도는 한 전투 내내 이어진다 (페이즈 전환·사망 재시작에서도 유지)."""
        self.part_durability = {
            name: durability
            for name, _, _, durability in BOSS_PARTS
            if durability is not None
        }

    def part_broken(self, name):
        return name in self.part_durability and self.part_durability[name] <= 0

    def pattern_available(self, pattern):
        part = PATTERN_PART.get(pattern)
        if part == "both_arms":
            return not (self.part_broken("arm_l") or self.part_broken("arm_r"))
        if part in self.part_durability:
            return not self.part_broken(part)
        return True

    def damage_part(self, name, amount):
        """팔 내구도를 깎는다. 이번에 부서졌으면 True."""
        if name not in self.part_durability or self.part_broken(name):
            return False
        self.part_durability[name] = max(0, self.part_durability[name] - amount)
        if self.part_durability[name] == 0:
            self._cancel_unavailable_pattern()
            return True
        return False

    def break_part(self, name):
        """디버그: 즉시 파괴. 이번에 부서졌으면 True."""
        if name not in self.part_durability or self.part_broken(name):
            return False
        return self.damage_part(name, self.part_durability[name])

    def _cancel_unavailable_pattern(self):
        # 부서진 팔은 이후 어떤 패턴에도 쓰이지 않는다 — 예고·실행 중이던 패턴이면 취소한다
        if self.current_pattern is None or self.pattern_available(self.current_pattern):
            return
        self.state = "rest"
        self.timer = self.PATTERN_GAP
        self.previous_pattern = self.current_pattern
        self.current_pattern = None
        self.target_lane = None
        self.target_x = None
        self.pending_rear_hits = []

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
        # 이번 패턴의 예고 시간 (페이즈 배율 적용, 패턴 시작 시 고정)
        self.current_telegraph = 0.0
        self.secondary_target_x = None
        # 아직 터지지 않은 뒷줄 시간차 타격: (공격 경과 시간, BossAttack)
        self.pending_rear_hits = []
        self.forward_progress = 0.0
        # 보스는 대좌에 결박돼 옆으로 움직이지 않는다. 판정·매몰선 x는 항상 중앙
        self.position_x = BOSS_HOME_X
        # 돌진 조준 오프셋(논리 x). 예고 시작 시 플레이어 쪽으로 정하고, 상체만 그쪽으로 기운다
        self.charge_lean_x = 0.0
        # 기울기 진행도 0~1: 예고 동안 0 → 1, 돌진·후경직 동안 1, 다음 공백 동안 1 → 0
        self.lean_progress = 0.0

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
                # 2페이즈 진입 연출이 끝나도 각성을 풀지 않는다 (2페이즈는 계속 각성)
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
                # 후경직이 끝나면 공백 시간 동안 상체를 다시 세운다
                self.lean_progress = max(
                    0.0,
                    self.lean_progress - fixed_delta / self.PATTERN_GAP,
                )
            if self.timer <= 1e-9:
                self._begin_pattern(phase, player_lane, player_x, rng, forced_pattern)
            return attacks

        if self.state == "telegraph":
            self.timer -= fixed_delta
            self.telegraph_elapsed += fixed_delta
            if self.current_pattern == "charge":
                # 예고 동안 플레이어 쪽으로 서서히 기운다
                self.lean_progress = min(
                    self.telegraph_elapsed / self.current_telegraph,
                    1.0,
                )
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
                self.lean_progress = 1.0
            attacks.extend(self._collect_attacks(self.attack_elapsed))
            if self.timer <= 1e-9:
                # 실행이 끝나기 전에 못 터진 뒷줄 타격이 있으면 여기서 마저 터뜨린다
                attacks.extend(attack for _, attack in self.pending_rear_hits)
                self.pending_rear_hits = []
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
        # 부서진 팔이 쓰던 패턴은 뺀다. 남은 가중치는 상대 비율 그대로 다시 나뉜다
        #   (rng.choices는 가중치 합으로 나눠 뽑으므로 재정규화가 자동이다)
        weights = {
            name: weight
            for name, weight in PHASE_PATTERNS[phase].items()
            if self.pattern_available(name)
        }
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
        self.pending_rear_hits = []
        if pattern in ("slam", "slam_double", "backhand"):
            # 조준은 예고 시작 시 플레이어 논리 x로 고정
            self.target_x = player_x
            self.target_lane = "platform_1"
        elif pattern == "charge":
            # 조준은 예고 시작에 고정. 판정 x는 기울기 오프셋 기준으로 계산한다
            self.charge_lean_x = player_x - BOSS_HOME_X
            self.lean_progress = 0.0
            self.target_x = BOSS_HOME_X + self.charge_lean_x
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
        # 페이즈 배율은 여기서 한 번만 곱한다. 매 프레임 곱하면 고정 타임스텝 타이밍이 흔들린다
        self.current_telegraph = telegraph_duration(pattern, phase)
        self.timer = self.current_telegraph
        self.telegraph_elapsed = 0.0

    @property
    def current_lean_x(self):
        """지금 상체가 기운 양(논리 x). 그리기 전용. 양 끝에서 부드럽게 감속한다."""
        t = self.lean_progress
        return self.charge_lean_x * t * t * (3.0 - 2.0 * t)

    def telegraph_is_visible(self):
        if self.state != "telegraph" or self.current_pattern is None:
            return False

        intervals = PATTERNS[self.current_pattern]["telegraph_blink"]
        # 깜빡임 간격도 줄어든 예고 시간에 맞춰 같은 비율로 줄인다 (1페이즈는 배율 1)
        ratio = self.current_telegraph / PATTERNS[self.current_pattern]["telegraph"]
        intervals = tuple(interval * ratio for interval in intervals) if ratio != 1.0 else intervals
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
            if self.current_pattern in ("slam", "slam_double"):
                # 같은 x의 뒷줄 타격을 SLAM_REAR_DELAY 뒤로 예약한다
                self.pending_rear_hits.append(
                    (
                        hit_times[self.next_hit_index] + SLAM_REAR_DELAY,
                        BossAttack(
                            pattern=self.current_pattern,
                            kind=pattern["kind"],
                            target_lane="platform_2",
                            target_x=target_x,
                            hitbox_width=pattern["hitbox_width"],
                            hit_index=self.next_hit_index,
                            delayed=True,
                        ),
                    )
                )
            self.next_hit_index += 1

        due = [hit for hit in self.pending_rear_hits if elapsed + 1e-9 >= hit[0]]
        if due:
            self.pending_rear_hits = [
                hit for hit in self.pending_rear_hits if hit not in due
            ]
            attacks.extend(attack for _, attack in due)
        return attacks
