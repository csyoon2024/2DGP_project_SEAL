"""타이틀·보스 사이 화면이 깔아 쓰는 배경. 전투 화면의 원근 배경을 그대로 재사용한다."""

import math

import arena_scene as arena
from arena_scene import HEIGHT, WIDTH


def draw_dim_arena(time, dim_alpha=170, sway=60.0):
    """보스·플레이어 없이 방·기둥·단상·발판만 그리고 검게 덮는다.

    time: 카메라를 천천히 좌우로 흔드는 데 쓰는 경과 시간(초). 0이면 정지 화면.
    """
    # 전투 카메라 전역을 이 화면용으로 맞춘다. ArenaScene은 생성 시 자기 값으로 되돌린다
    arena.view_zoom = 1.0
    arena.camera_x = math.sin(time * 0.25) * sway
    arena.DRAW_OFFSET_X = 0
    arena.DRAW_OFFSET_Y = 0

    arena.draw_void()
    arena.draw_room(with_floor=False)
    arena.draw_pillars(with_floor=False)
    arena.draw_back_fog()
    arena.draw_boss_backlight(0.0)
    arena.draw_pedestal()
    arena.draw_lane("platform_1", "front_lane", "front_edge", 8)
    arena.draw_lane("platform_2", "rear_lane", "rear_edge", 10)

    dim = (0, 0, 0, dim_alpha)
    arena.draw_polygon(
        ((0, 0), (WIDTH, 0), (WIDTH, HEIGHT), (0, HEIGHT)),
        (dim, dim, dim, dim),
    )
