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
Press `F1` to toggle the debug panel, `F2` to show collision boxes, `F3` to
toggle invulnerability, `F4` to reset the player, and `H` with the panel open to
test a hit. Press `Esc` to close the game. Boss behavior is planned for a later
step.