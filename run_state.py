"""전투와 전투 사이에 이어지는 플레이어 상태 (한 번의 플레이 = 한 런)."""

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BattleRecord:
    """한 전투의 결과. ArenaScene이 처치 직후 만들어 InterludeScene에 넘긴다."""

    elapsed: float  # 전투 소요 시간(초). 사망 후 재시작한 시간도 포함한다
    hits_taken: int  # 피격 횟수 (무적·회피로 막은 공격은 세지 않는다)
    health_left: int
    max_health: int


@dataclass(frozen=True)
class Skill:
    skill_id: str
    name: str
    description: str  # 카드에 그대로 줄바꿈해서 쓴다


# 획득 기술 후보. 아직 효과는 구현하지 않는다 — 선택해서 RunState.skills에 저장하는 데까지만
SKILL_POOL = (
    Skill("seal_strike", "봉인 강타", "강공격이 게이지를\n더 크게 밀어낸다"),
    Skill("swift_step", "질풍 회피", "회피 재사용 대기시간이\n짧아진다"),
    Skill("iron_will", "강철 의지", "최대 체력이\n1칸 늘어난다"),
    Skill("chain_echo", "쇠사슬 메아리", "기본 공격 3연속 적중 시\n게이지를 한 번 더 민다"),
    Skill("leap", "도약", "플랫폼 이동이\n더 빨라진다"),
    Skill("ward", "결계", "피격 시 밀리는\n게이지가 줄어든다"),
)
SKILL_CHOICE_COUNT = 3
# 전투 순서. 마지막 보스를 잡은 뒤에는 마지막 보스를 다시 띄운다 (보스가 더 생기면 여기에 추가)
BOSS_ORDER = (1, 2)


@dataclass
class RunState:
    skills: list = field(default_factory=list)  # 고른 Skill들, 고른 순서대로
    records: list = field(default_factory=list)  # 지난 전투들의 BattleRecord
    battles_cleared: int = 0

    def skill_choices(self, rng=None):
        """아직 없는 기술 중 SKILL_CHOICE_COUNT개. 남은 게 모자라면 전체에서 뽑는다."""
        rng = rng or random.Random()
        owned = {skill.skill_id for skill in self.skills}
        pool = [skill for skill in SKILL_POOL if skill.skill_id not in owned]
        if len(pool) < SKILL_CHOICE_COUNT:
            pool = list(SKILL_POOL)
        return rng.sample(pool, SKILL_CHOICE_COUNT)

    def next_boss_id(self):
        return BOSS_ORDER[min(self.battles_cleared, len(BOSS_ORDER) - 1)]

    def record_battle(self, record):
        self.records.append(record)
        self.battles_cleared += 1

    def add_skill(self, skill):
        self.skills.append(skill)
