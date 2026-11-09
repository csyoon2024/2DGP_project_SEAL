from arena_scene import ArenaScene
from game_framework import GameFramework


def main():
    game = GameFramework()
    game.run(ArenaScene())


if __name__ == "__main__":
    main()