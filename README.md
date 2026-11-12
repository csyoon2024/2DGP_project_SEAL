# 2DGP_project_SEAL

## Seal Prototype

A pico2d prototype for the two-lane perspective arena described in `PRD.md`.
The current build uses colored geometry as temporary art and opens directly to
the arena layout.

### Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use the left/right arrows or `A`/`D` to move. Press `J` for a basic attack, `K`
for a heavy attack, `Space` to dodge, and either `Shift` key to switch platforms.
Press `F1` to toggle the debug panel and `Esc` to close the game. Boss behavior
is planned for a later step.