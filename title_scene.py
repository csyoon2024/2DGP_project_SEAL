import pico2d

from arena_scene import HEIGHT, WIDTH
from run_state import RunState
from scene_backdrop import draw_dim_arena
from ui_text import draw_text

# 키를 누르라는 문구의 깜빡임 주기(초). 켜짐 0.7 / 꺼짐 0.3
PROMPT_BLINK_PERIOD = 1.0
PROMPT_BLINK_ON = 0.7


class TitleScene:
    def __init__(self, scene_manager):
        self.scene_manager = scene_manager
        self.elapsed = 0.0

    def enter(self):
        self.elapsed = 0.0

    def exit(self):
        pass

    def handle_event(self, event):
        # ESC는 GameFramework가 먼저 가져가 종료하므로 여기 오는 키는 전부 "시작"이다
        if event.type in (pico2d.SDL_KEYDOWN, pico2d.SDL_MOUSEBUTTONDOWN):
            self.start_run()

    def start_run(self):
        from arena_scene import ArenaScene

        self.scene_manager.change_scene(ArenaScene(self.scene_manager, RunState()))

    def update(self, fixed_delta):
        self.elapsed += fixed_delta

    def draw(self):
        draw_dim_arena(self.elapsed)
        draw_text(WIDTH / 2, HEIGHT / 2 + 90, "봉인", 96, (240, 230, 215), bold=True, align="center")
        draw_text(WIDTH / 2, HEIGHT / 2 + 10, "S E A L", 26, (224, 28, 44), bold=True, align="center")
        if self.elapsed % PROMPT_BLINK_PERIOD < PROMPT_BLINK_ON:
            draw_text(WIDTH / 2, HEIGHT / 2 - 120, "아무 키나 누르세요", 24, (190, 196, 210), align="center")
        draw_text(WIDTH / 2, 40, "ESC 종료", 16, (110, 116, 130), align="center")
