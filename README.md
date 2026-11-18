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

Use the left/right arrows or `A`/`D` to move. Left-click for a basic attack,
right-click for a heavy attack, either `Shift` key to dodge, and `Space` to switch platforms.
The fight starts on the rear platform.
Press `F1` to toggle the debug panel, `F2` to show collision boxes, `F3` to
toggle invulnerability, `F4` to reset the player, and `H` with the panel open to
test a hit. `F5` requests a phase jump, `[`/`]` adjust the debug gauge, `F6`
cycles a forced pattern, and `F7` toggles a fixed random seed. Press `Esc` to
close the game. Boss 1 has two phases with slam, charge, shockwave, missile, and
double-slam patterns. Push the shared gauge to the left to clear each phase.

The game opens on a title screen; press any key to start. After the boss is
defeated, a results screen shows the fight time, hits taken, and remaining
health, then offers three skills: pick one with the left/right arrows (or the
mouse) and press `Enter` to start the next fight. Skills are stored on the run
but have no effect yet.