import time

import pico2d


CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
FIXED_DELTA = 1.0 / 60.0
MAX_FRAME_DELTA = 0.25


class GameFramework:
    def __init__(self, scene_manager):
        # 씬을 직접 받지 않고 SceneManager를 받는다. 첫 씬은 main.py가 넣어 둔다
        self.scene_manager = scene_manager
        self.running = False
        self.canvas_open = False

    def open(self):
        pico2d.open_canvas(CANVAS_WIDTH, CANVAS_HEIGHT, sync=True)
        self.canvas_open = True

        if hasattr(pico2d, "hide_lattice"):
            pico2d.hide_lattice()

        canvas_state = pico2d.open_canvas.__globals__
        renderer = canvas_state.get("renderer")
        if renderer is not None:
            pico2d.SDL_SetRenderDrawBlendMode(
                renderer,
                pico2d.SDL_BLENDMODE_BLEND,
            )

        self._configure_fullscreen()

    def _configure_fullscreen(self):
        set_fullscreen = getattr(pico2d, "SDL_SetWindowFullscreen", None)
        fullscreen_flag = getattr(pico2d, "SDL_WINDOW_FULLSCREEN_DESKTOP", None)
        set_logical_size = getattr(pico2d, "SDL_RenderSetLogicalSize", None)
        canvas_state = pico2d.open_canvas.__globals__
        window = canvas_state.get("window")
        renderer = canvas_state.get("renderer")

        if all((set_fullscreen, fullscreen_flag, set_logical_size, window, renderer)):
            set_logical_size(renderer, CANVAS_WIDTH, CANVAS_HEIGHT)
            set_fullscreen(window, fullscreen_flag)
        else:
            print("Fullscreen SDL helpers unavailable; using a 1280x720 window.")

    def run(self):
        self.open()
        self.running = True
        previous_time = time.perf_counter()
        accumulator = 0.0

        try:
            while self.running:
                current_time = time.perf_counter()
                frame_delta = min(current_time - previous_time, MAX_FRAME_DELTA)
                previous_time = current_time
                accumulator += frame_delta

                for event in pico2d.get_events():
                    if event.type == pico2d.SDL_QUIT:
                        self.running = False
                    elif (
                        event.type == pico2d.SDL_KEYDOWN
                        and event.key == pico2d.SDLK_ESCAPE
                    ):
                        self.running = False
                    else:
                        self.scene_manager.handle_event(event)

                while accumulator >= FIXED_DELTA:
                    self.scene_manager.update(FIXED_DELTA)
                    accumulator -= FIXED_DELTA

                # 씬 매니저 없이 단독 실행된 씬이 종료를 요청하면 게임을 닫는다
                if getattr(self.scene_manager.current_scene, "quit_requested", False):
                    self.running = False

                pico2d.clear_canvas()
                self.scene_manager.draw()
                pico2d.update_canvas()
        finally:
            self.close()

    def close(self):
        if self.canvas_open:
            pico2d.close_canvas()
            self.canvas_open = False