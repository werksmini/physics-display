# Falling sand

![preview](preview.png)

Pour sand and water, build with stone, and watch it pile, flow and settle. In the spirit of *The Powder Toy* and *Sandspiel*.

```bash
python run.py sand            # Pi
python run.py sand --window   # laptop
```

## Touch

Pick a material from the **palette at the top** (Sand, Water, Stone, Erase), then draw with your finger. **Restart scene** in the panel clears the board (or turn off **Start with a demo layout** for a blank board).

## How it works

A **cellular automaton**: the screen is a grid and every cell follows a few local rules each step.

- **Sand** falls straight down if it can, otherwise slides diagonally. It sinks through water (they swap places).
- **Water** falls, slides diagonally, then spreads sideways, so it finds its level.
- **Stone** never moves.

Everything updates at once with NumPy array shifts. The trick that makes this safe: each pass moves material in only *one* direction (chosen at random each step), so two grains can never claim the same empty cell. A little randomness stops piles from looking too regular.

## Settings worth playing with

| Setting | Try |
|---|---|
| Water spread | 0 for thick sludge; 6 for very runny water |
| Simulation speed | Higher for faster falling |
| Grain size | 2 for fine sand (slower); 6–8 for chunky |

## Ideas

- Fire that burns wood and turns water to steam
- Plants that grow when watered
- Tilt: let gravity follow the touch direction
