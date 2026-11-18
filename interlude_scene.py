"""보스 사이 화면 — 전투 결과와 획득 기술 선택. 걸어다니는 공간이 아닌 정지 화면 한 장."""

import pico2d

import arena_scene as arena
from arena_scene import HEIGHT, WIDTH
from scene_backdrop import draw_dim_arena
from ui_text import draw_text

# 카드 배치 (화면 아래쪽). 3장 × 300px + 간격 2 × 40px = 980px, 가운데 정렬
CARD_WIDTH = 300
CARD_HEIGHT = 230
CARD_GAP = 40
CARD_BOTTOM = 110
# 고른 카드를 이만큼 들어 올려 선택이 한눈에 보이게 한다
CARD_RAISE = 14
# 전투가 끝나는 순간 누르고 있던 키(이동·공격)로 카드가 바로 결정되지 않게 입력을 잠깐 막는다
INPUT_DELAY = 0.4

TEXT = (240, 230, 215)
TEXT_DIM = (150, 156, 170)
ACCENT = (255, 107, 53)
HEALTH_ON = (255, 107, 53)
HEALTH_OFF = (42, 48, 65)


def format_time(seconds):
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:04.1f}"


class InterludeScene:
    def __init__(self, scene_manager, run_state, record):
        self.scene_manager = scene_manager
        self.run_state = run_state
        self.record = record
        self.choices = run_state.skill_choices()
        self.selected = 1  # 가운데 카드에서 시작
        self.elapsed = 0.0

    def enter(self):
        self.elapsed = 0.0

    def exit(self):
        pass

    # --- 입력 ---------------------------------------------------------------
    def handle_event(self, event):
        if self.elapsed < INPUT_DELAY:
            return
        if event.type == pico2d.SDL_KEYDOWN:
            if event.key in (pico2d.SDLK_LEFT, pico2d.SDLK_a):
                self.selected = (self.selected - 1) % len(self.choices)
            elif event.key in (pico2d.SDLK_RIGHT, pico2d.SDLK_d):
                self.selected = (self.selected + 1) % len(self.choices)
            elif event.key in (pico2d.SDLK_RETURN, pico2d.SDLK_KP_ENTER, pico2d.SDLK_SPACE):
                self.confirm()
        elif event.type == pico2d.SDL_MOUSEMOTION:
            index = self.card_at(event.x, HEIGHT - 1 - event.y)
            if index is not None:
                self.selected = index
        elif event.type == pico2d.SDL_MOUSEBUTTONDOWN and event.button == pico2d.SDL_BUTTON_LEFT:
            index = self.card_at(event.x, HEIGHT - 1 - event.y)
            if index is not None:
                self.selected = index
                self.confirm()

    def confirm(self):
        from arena_scene import ArenaScene

        self.run_state.add_skill(self.choices[self.selected])
        # 다음 전투. 아직 보스가 하나뿐이라 같은 보스를 다시 띄운다
        self.scene_manager.change_scene(ArenaScene(self.scene_manager, self.run_state))

    # --- 배치 ---------------------------------------------------------------
    def card_rect(self, index):
        total = len(self.choices) * CARD_WIDTH + (len(self.choices) - 1) * CARD_GAP
        left = (WIDTH - total) / 2 + index * (CARD_WIDTH + CARD_GAP)
        bottom = CARD_BOTTOM + (CARD_RAISE if index == self.selected else 0)
        return left, bottom, left + CARD_WIDTH, bottom + CARD_HEIGHT

    def card_at(self, x, y):
        for index in range(len(self.choices)):
            left, bottom, right, top = self.card_rect(index)
            if left <= x <= right and bottom <= y <= top:
                return index
        return None

    def update(self, fixed_delta):
        self.elapsed += fixed_delta

    # --- 그리기 -------------------------------------------------------------
    def draw(self):
        draw_dim_arena(0.0, dim_alpha=200)
        self.draw_results()
        self.draw_cards()
        draw_text(WIDTH / 2, 50, "← →  선택      Enter  결정", 18, TEXT_DIM, align="center")

    def draw_results(self):
        record = self.record
        draw_text(WIDTH / 2, 640, "봉인 완료", 44, TEXT, bold=True, align="center")
        draw_text(WIDTH / 2, 592, f"전투 {self.run_state.battles_cleared}", 18, TEXT_DIM, align="center")

        # 결과 3칸: 소요 시간 / 피격 횟수 / 남은 체력
        columns = (WIDTH / 2 - 300, WIDTH / 2, WIDTH / 2 + 300)
        label_y, value_y = 530, 486
        for x, label in zip(columns, ("소요 시간", "피격 횟수", "남은 체력")):
            draw_text(x, label_y, label, 18, TEXT_DIM, align="center")
        draw_text(columns[0], value_y, format_time(record.elapsed), 34, TEXT, bold=True, align="center")
        draw_text(columns[1], value_y, f"{record.hits_taken}회", 34, TEXT, bold=True, align="center")
        # 남은 체력은 전투 화면의 체력 아이콘과 같은 원으로
        spacing = 30
        start = columns[2] - spacing * (record.max_health - 1) / 2
        for index in range(record.max_health):
            arena.set_draw_rgb(*(HEALTH_ON if index < record.health_left else HEALTH_OFF))
            arena.draw_filled_circle(start + index * spacing, value_y, 10)

        arena.set_draw_rgb(*TEXT_DIM, 80)
        arena.draw_line(WIDTH / 2 - 420, 420, WIDTH / 2 + 420, 420)
        draw_text(WIDTH / 2, 385, "획득할 기술을 고르세요", 22, TEXT, align="center")

    def draw_cards(self):
        for index, skill in enumerate(self.choices):
            left, bottom, right, top = self.card_rect(index)
            chosen = index == self.selected
            fill = (34, 30, 30, 240) if chosen else (18, 21, 31, 230)
            arena.draw_polygon(
                ((left, bottom), (right, bottom), (right, top), (left, top)),
                (fill, fill, fill, fill),
            )
            if chosen:
                arena.set_draw_rgb(*ACCENT)
                arena.draw_rectangle(left, bottom, right, top)
                arena.draw_rectangle(left + 1, bottom + 1, right - 1, top - 1)
            else:
                arena.set_draw_rgb(74, 84, 110)
                arena.draw_rectangle(left, bottom, right, top)

            center_x = (left + right) / 2
            draw_text(center_x, top - 50, skill.name, 28, ACCENT if chosen else TEXT, bold=True, align="center")
            arena.set_draw_rgb(*TEXT_DIM, 70)
            arena.draw_line(left + 40, top - 88, right - 40, top - 88)
            for line_index, line in enumerate(skill.description.split("\n")):
                draw_text(center_x, top - 125 - line_index * 30, line, 19, TEXT if chosen else TEXT_DIM, align="center")
