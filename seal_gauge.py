class SealGauge:
    INITIAL_VALUE = 0.5
    LEAK_PER_SECOND = 0.015
    BASIC_ATTACK_GAIN = 0.04
    HEAVY_ATTACK_GAIN = 0.12
    BOSS_HIT_LOSS = 0.15
    AWAKENED_HIT_LOSS = 0.20
    AWAKEN_THRESHOLD = 0.85
    AWAKEN_CLEAR_THRESHOLD = 0.60

    def __init__(self):
        self.value = self.INITIAL_VALUE
        self.boss_awakened = False

    @property
    def player_won(self):
        return self.value <= 0.0

    @property
    def boss_won(self):
        return self.value >= 1.0

    def update(self, fixed_delta):
        if not self.player_won and not self.boss_won:
            self.value = min(1.0, self.value + self.LEAK_PER_SECOND * fixed_delta)
        self._update_awakened_state()

    def player_attack_hit(self, attack_type):
        if self.player_won or self.boss_won:
            return

        gain = (
            self.HEAVY_ATTACK_GAIN
            if attack_type == "heavy"
            else self.BASIC_ATTACK_GAIN
        )
        self.value = max(0.0, self.value - gain)
        self._update_awakened_state()

    def player_hit(self, loss=None):
        if self.player_won or self.boss_won:
            return

        hit_loss = self.BOSS_HIT_LOSS if loss is None else loss
        self.value = min(1.0, self.value + hit_loss)
        self._update_awakened_state()

    def set_debug_value(self, value):
        self.value = max(0.0, min(float(value), 1.0))
        self._update_awakened_state()

    def _update_awakened_state(self):
        if self.boss_awakened:
            if self.value <= self.AWAKEN_CLEAR_THRESHOLD:
                self.boss_awakened = False
        elif self.value >= self.AWAKEN_THRESHOLD:
            self.boss_awakened = True