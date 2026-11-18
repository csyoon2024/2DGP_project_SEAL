from game_framework import GameFramework
from scene_manager import SceneManager
from title_scene import TitleScene


def main():
    # 타이틀 → 전투(ArenaScene) → 보스 사이 화면(InterludeScene) → 전투 ...
    scene_manager = SceneManager()
    scene_manager.change_scene(TitleScene(scene_manager))
    game = GameFramework(scene_manager)
    game.run()


if __name__ == "__main__":
    main()
