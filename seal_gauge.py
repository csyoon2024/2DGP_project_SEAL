from boss import PHASE_MODIFIERS


class SealGauge:
    INITIAL_VALUE = 0.5
    LEAK_PER_SECOND = 0.015
    BASIC_ATTACK_GAIN = 0.04
    HEAVY_ATTACK_GAIN = 0.12
    # 테스트용: 공격으로 미는 양 배율. 3.0 = 300% (기본 0.04 → 0.12, 강공격 0.12 → 0.36).
    #   페이즈 전환·회복을 빨리 확인하려고 임시로 올렸다. 밸런스 확인 전에 1.0으로 되돌릴 것
    ATTACK_GAIN_TEST_MULTIPLIER = 3.0
    # 게이지 변화량 전체 배율 0.5: 게이지가 너무 빨리 오간다는 플레이 피드백으로 절반으로 낮췄다.
    #   공격으로 미는 양(기세 표 포함)과 피격·사망 패널티로 밀리는 양에 똑같이 곱한다.
    #   누수(LEAK_PER_SECOND)는 넣지 않았다 — 누수를 줄이면 순수지 구조가 바뀐다
    GAUGE_CHANGE_SCALE = 0.5
    # 1페이즈 기준값. 실제 피격 손실·각성 진입선은 PHASE_MODIFIERS에서 페이즈별로 가져온다
    BOSS_HIT_LOSS = 0.15
    AWAKENED_HIT_LOSS = 0.20
    # 해제선은 페이즈와 무관하게 고정. 진입선과 벌어져 있어야 경계에서 깜빡이지 않는다
    AWAKEN_CLEAR_THRESHOLD = 0.60
    # 최저점(보스 쪽으로 가장 많이 밀린 값)에서 이만큼 되밀면 체력 1칸 회복.
    # 절대 위치가 아니라 "되민 양" 기준이라 깊은 열세에서도 회복이 잠기지 않는다.
    # 0.25 = 강공격 2회 + 기본공격 1회 정도. 피격 1회(0.15~0.20)보다 커서
    # 맞은 만큼 바로 되찾는 무한 회복은 막고, 꾸준히 때리면 회복되는 정도로 시작한다
    HEALTH_RECOVER_PUSHBACK = 0.25

    # 기세(momentum)별 게이지 획득량. 인덱스 = 기세 0~4.
    #   앞줄에서 적중할 때마다 기세가 1 오르고, 피격하면 0이 된다 (ArenaScene).
    #   앞줄에 머물며 맞지 않고 계속 때릴수록 많이 밀지만, 한 대 맞으면 쌓은 걸 다 잃는 도박.
    #   기세 0 칸은 기존 상수 그대로라 기세 0으로만 플레이하면 전과 완전히 같다.
    #   기본 공격 4% → 12% (+2%씩, 최대 3배), 강공격 12% → 20% (+2%씩, 최대 1.67배):
    #   같은 폭으로 올려 연타형 기본 공격 쪽이 기세의 이득을 더 크게 본다
    MOMENTUM_MAX = 4
    MOMENTUM_BASIC_GAINS = (BASIC_ATTACK_GAIN, 0.06, 0.08, 0.10, 0.12)
    MOMENTUM_HEAVY_GAINS = (HEAVY_ATTACK_GAIN, 0.14, 0.16, 0.18, 0.20)

    def __init__(self):
        self.value = self.INITIAL_VALUE
        self.phase = 1
        self.boss_awakened = False
        # 회복 기준점: 마지막 회복(또는 체력이 가득했던 때) 이후 가장 보스 쪽으로 밀린 값
        self.recovery_mark = self.value

    @property
    def player_won(self):
        return self.value <= 0.0

    @property
    def boss_won(self):
        # 디버그 패널 표시용. 패배 조건이 아니다 — 끝에 닿아도 각성 상태로 계속 싸운다
        return self.value >= 1.0

    def update(self, fixed_delta):
        if not self.player_won:
            self.value = min(1.0, self.value + self.LEAK_PER_SECOND * fixed_delta)
            self._update_recovery_mark()
        self._update_awakened_state()

    def attack_gain(self, attack_type, momentum=0):
        """적중 1회가 게이지를 미는 실제 양 (기세 표 × 테스트 배율)."""
        table = (
            self.MOMENTUM_HEAVY_GAINS
            if attack_type == "heavy"
            else self.MOMENTUM_BASIC_GAINS
        )
        momentum = max(0, min(int(momentum), self.MOMENTUM_MAX))
        return table[momentum] * self.ATTACK_GAIN_TEST_MULTIPLIER * self.GAUGE_CHANGE_SCALE

    def player_attack_hit(self, attack_type, momentum=0):
        # 보스 쪽 끝(1.0)에서도 공격이 게이지를 되밀 수 있어야 하므로 player_won만 막는다
        if self.player_won:
            return

        # 공격은 value를 빼는 방향 (0 = 플레이어 승리)
        self.value = max(0.0, self.value - self.attack_gain(attack_type, momentum))
        self._update_awakened_state()

    def push_toward_player(self, amount):
        """일회성 보상(부위 파괴 등). 공격과 같은 척도라 GAUGE_CHANGE_SCALE이 곱해진다."""
        if self.player_won:
            return
        self.value = max(0.0, self.value - amount * self.GAUGE_CHANGE_SCALE)
        self._update_awakened_state()

    def player_hit(self, loss=None):
        if self.player_won:
            return

        hit_loss = self.BOSS_HIT_LOSS if loss is None else loss
        self.value = min(1.0, self.value + hit_loss * self.GAUGE_CHANGE_SCALE)
        self._update_recovery_mark()
        self._update_awakened_state()

    def set_debug_value(self, value):
        self.value = max(0.0, min(float(value), 1.0))
        self.reset_recovery_mark()
        self._update_awakened_state()

    def try_recover_health(self):
        """최저점에서 HEALTH_RECOVER_PUSHBACK 이상 되밀었으면 기준점을 현재값으로 갱신하고 True."""
        if self.value <= self.recovery_mark - self.HEALTH_RECOVER_PUSHBACK + 1e-9:
            self.reset_recovery_mark()
            return True
        return False

    def reset_recovery_mark(self):
        self.recovery_mark = self.value

    def _update_recovery_mark(self):
        self.recovery_mark = max(self.recovery_mark, self.value)

    def _update_awakened_state(self):
        if self.boss_awakened:
            if self.value <= self.AWAKEN_CLEAR_THRESHOLD:
                self.boss_awakened = False
        elif self.value >= self.awaken_threshold:
            self.boss_awakened = True

    @property
    def awaken_threshold(self):
        return PHASE_MODIFIERS[self.phase]["awaken_threshold"]

    def set_phase(self, phase):
        self.phase = phase
        self._update_awakened_state()

    def hit_loss(self, awakened):
        """현재 페이즈의 피격 손실. 각성 중 손실은 기본 손실과 같은 비율로 올린다."""
        base = PHASE_MODIFIERS[self.phase]["hit_loss"]
        if awakened:
            return self.AWAKENED_HIT_LOSS * (base / self.BOSS_HIT_LOSS)
        return base
