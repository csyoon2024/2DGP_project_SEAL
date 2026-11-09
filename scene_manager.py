class SceneManager:
    def __init__(self):
        self.current_scene = None

    def change_scene(self, next_scene):
        if self.current_scene is not None:
            self.current_scene.exit()

        self.current_scene = next_scene
        self.current_scene.enter()

    def handle_event(self, event):
        if self.current_scene is not None:
            self.current_scene.handle_event(event)

    def update(self, fixed_delta):
        if self.current_scene is not None:
            self.current_scene.update(fixed_delta)

    def draw(self):
        if self.current_scene is not None:
            self.current_scene.draw()