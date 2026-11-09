import pico2d

from pico2d import (
    draw_circle as pico_draw_circle,
    draw_line as pico_draw_line,
    draw_rectangle as pico_draw_rectangle,
)


WIDTH = 1280
HEIGHT = 720

COLORS = {
    "background": (17, 22, 23),
    "wall": (27, 35, 35),
    "wall_light": (43, 53, 49),
    "floor": (31, 39, 38),
    "floor_line": (52, 62, 57),
    "rear_lane": (37, 61, 58),
    "rear_edge": (101, 151, 129),
    "front_lane": (54, 68, 58),
    "front_edge": (177, 190, 130),
    "accent": (235, 119, 86),
    "accent_light": (255, 195, 126),
    "actor_dark": (18, 24, 25),
    "actor": (225, 112, 78),
    "actor_light": (247, 211, 165),
    "shadow": (20, 27, 26),
}

LANES = {
    "platform_2": {
        "left": 0,
        "right": WIDTH,
        "bottom": 0,
        "top": 120,
        "center_y": 60,
        "scale": 1.0,
    },
    "platform_1": {
        "left": 0,
        "right": WIDTH,
        "bottom": 195,
        "top": 285,
        "center_y": 240,
        "scale": 0.71,
    },
}

PLAYER_SPEED = 320
PLAYER_LOGICAL_WIDTH = 900
PLAYER_X_MIN = 25
PLAYER_X_MAX = PLAYER_LOGICAL_WIDTH - PLAYER_X_MIN


def set_draw_color(name):
    global active_color
    active_color = COLORS[name]


def draw_filled_circle(x, y, radius):
    pico_draw_circle(
        int(round(x)),
        int(round(y)),
        max(1, int(round(radius))),
        *active_color,
        filled=True,
    )


def draw_filled_rectangle(left, bottom, right, top):
    pico_draw_rectangle(
        int(round(left)),
        int(round(bottom)),
        int(round(right)),
        int(round(top)),
        *active_color,
        filled=True,
    )


def draw_line(x1, y1, x2, y2):
    pico_draw_line(
        int(round(x1)),
        int(round(y1)),
        int(round(x2)),
        int(round(y2)),
        *active_color,
    )


def draw_rectangle(left, bottom, right, top):
    pico_draw_rectangle(
        int(round(left)),
        int(round(bottom)),
        int(round(right)),
        int(round(top)),
        *active_color,
    )


def draw_room():
    set_draw_color("background")
    draw_filled_rectangle(0, 0, WIDTH, HEIGHT)

    set_draw_color("wall")
    draw_filled_rectangle(0, 430, WIDTH, HEIGHT)

    set_draw_color("wall_light")
    draw_line(0, 430, WIDTH, 430)
    draw_line(0, 610, WIDTH, 610)
    for panel_x in range(80, WIDTH, 160):
        draw_line(panel_x, 475, panel_x, 700)

    set_draw_color("floor")
    draw_filled_rectangle(0, 0, WIDTH, 430)

    set_draw_color("floor_line")
    for floor_y in (35, 430):
        draw_line(0, floor_y, WIDTH, floor_y)
    for floor_x in range(0, WIDTH + 1, 160):
        draw_line(floor_x, 0, floor_x, 430)

    set_draw_color("wall_light")
    draw_rectangle(112, 0, 1168, 602)
    draw_line(112, 404, 1168, 404)


def draw_lane(lane, fill_color, edge_color, tick_count):
    left = lane["left"]
    right = lane["right"]
    bottom = lane["bottom"]
    top = lane["top"]
    center_y = lane["center_y"]

    set_draw_color(fill_color)
    draw_filled_rectangle(left, bottom, right, top)

    set_draw_color(edge_color)
    draw_rectangle(left, bottom, right, top)
    draw_line(left, center_y, right, center_y)

    tick_step = (right - left) / tick_count
    for tick in range(1, tick_count):
        tick_x = left + tick * tick_step
        draw_line(tick_x, bottom + 12, tick_x, top - 12)

    marker_radius = max(3, int(5 * lane["scale"]))
    for marker_x in (left + 18, right - 18):
        draw_filled_circle(marker_x, center_y, marker_radius)


def draw_perspective_rails():
    platform_2 = LANES["platform_2"]
    platform_1 = LANES["platform_1"]

    set_draw_color("wall_light")
    draw_line(
        platform_2["left"],
        platform_2["bottom"],
        platform_1["left"],
        platform_1["bottom"],
    )
    draw_line(
        platform_2["right"],
        platform_2["bottom"],
        platform_1["right"],
        platform_1["bottom"],
    )

    set_draw_color("floor_line")
    draw_line(
        platform_2["left"],
        platform_2["top"],
        platform_1["left"],
        platform_1["top"],
    )
    draw_line(
        platform_2["right"],
        platform_2["top"],
        platform_1["right"],
        platform_1["top"],
    )


def draw_boss_marker():
    set_draw_color("actor_dark")
    draw_filled_circle(640, 480, 38)
    set_draw_color("accent")
    draw_filled_circle(640, 480, 28)
    set_draw_color("actor_dark")
    draw_filled_circle(640, 480, 20)
    set_draw_color("accent_light")
    draw_line(640, 449, 640, 511)
    draw_line(609, 480, 671, 480)
    draw_filled_circle(640, 480, 5)


def draw_player_placeholder(screen_x, foot_y, scale):
    head_radius = 12 * scale
    body_half_width = 13 * scale
    body_bottom = foot_y + 17 * scale
    body_top = foot_y + 56 * scale
    shoulder_y = foot_y + 49 * scale

    set_draw_color("shadow")
    draw_filled_circle(screen_x - 17 * scale, foot_y + 3 * scale, 4 * scale)
    draw_filled_rectangle(
        screen_x - 17 * scale,
        foot_y - scale,
        screen_x + 17 * scale,
        foot_y + 7 * scale,
    )
    draw_filled_circle(screen_x + 17 * scale, foot_y + 3 * scale, 4 * scale)

    set_draw_color("actor_dark")
    draw_filled_circle(screen_x, foot_y + 70 * scale, 15 * scale)
    draw_filled_rectangle(
        screen_x - body_half_width - 3 * scale,
        body_bottom - 3 * scale,
        screen_x + body_half_width + 3 * scale,
        body_top + 3 * scale,
    )

    set_draw_color("actor")
    draw_filled_circle(screen_x, foot_y + 70 * scale, head_radius)
    draw_filled_rectangle(
        screen_x - body_half_width,
        body_bottom,
        screen_x + body_half_width,
        body_top,
    )
    draw_line(
        screen_x - body_half_width,
        shoulder_y,
        screen_x - 22 * scale,
        foot_y + 31 * scale,
    )
    draw_line(
        screen_x + body_half_width,
        shoulder_y,
        screen_x + 22 * scale,
        foot_y + 31 * scale,
    )

    set_draw_color("actor_light")
    draw_filled_circle(screen_x, foot_y + 70 * scale, 5 * scale)
    draw_line(
        screen_x - 7 * scale,
        foot_y + 18 * scale,
        screen_x - 10 * scale,
        foot_y + 2 * scale,
    )
    draw_line(
        screen_x + 7 * scale,
        foot_y + 18 * scale,
        screen_x + 10 * scale,
        foot_y + 2 * scale,
    )


class ArenaScene:
    def __init__(self):
        self.player_lane = "platform_1"
        self.player_logical_x = 240
        self.pressed_keys = set()

    def enter(self):
        pass

    def exit(self):
        pass

    def handle_event(self, event):
        if event.type == pico2d.SDL_KEYDOWN:
            self.pressed_keys.add(event.key)
        elif event.type == pico2d.SDL_KEYUP:
            self.pressed_keys.discard(event.key)

    def update(self, fixed_delta):
        move_right = any(
            key in self.pressed_keys for key in (pico2d.SDLK_RIGHT, pico2d.SDLK_d)
        )
        move_left = any(
            key in self.pressed_keys for key in (pico2d.SDLK_LEFT, pico2d.SDLK_a)
        )
        move_direction = int(move_right) - int(move_left)
        self.player_logical_x += move_direction * PLAYER_SPEED * fixed_delta
        self.player_logical_x = max(
            PLAYER_X_MIN,
            min(self.player_logical_x, PLAYER_X_MAX),
        )

    def draw(self):
        draw_room()
        draw_perspective_rails()
        draw_lane(LANES["platform_2"], "rear_lane", "rear_edge", 10)
        draw_lane(LANES["platform_1"], "front_lane", "front_edge", 8)
        draw_boss_marker()

        lane = LANES[self.player_lane]
        screen_width = lane["right"] - lane["left"]
        screen_x = (
            lane["left"]
            + self.player_logical_x * screen_width / PLAYER_LOGICAL_WIDTH
        )
        draw_player_placeholder(screen_x, lane["center_y"], lane["scale"])