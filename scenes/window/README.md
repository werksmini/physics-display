# Foggy car window

![preview](preview.png)

**Landscape.** The passenger seat of a small classic 1970s sedan with a black interior, on a damp day in mountain farm country. The side window is fogged up; wipe it with your finger to see out. The fog slowly comes back.

The framing follows a photo taken in a BMW 2002, from a slightly higher eye height:
- a thin sliver of windshield at the left, with the wiper sweeping
- a thick black A-pillar running up into a black headliner
- the triangular vent window with a chrome divider, then the big side window
- a rectangular chrome mirror just past the divider, its reflection streaming with the passing fields
- a black pleated door panel with a chrome lock button, an angled door pull and a window crank

No badges or lettering.

```bash
python run.py window            # Pi: hold the screen sideways (Flip landscape in the panel turns it the other way)
python run.py window --window   # laptop: opens a landscape window
```

## Touch

Swipe to wipe the condensation away: you're drawing on the window. Droplets gather at the edges of your wipes and run down the glass.

## How it works

- **Parallax:** the scenery is a stack of looping layers, each moving at its own fraction of the driving speed, slowest far away:

  | Layer | Speed |
  |---|---|
  | Low clouds (also drifting on their own) | 1.5% |
  | Far mountains | 3% |
  | Near mountains, with mist at their feet | 6% |
  | Wooded hill line | 14% |
  | Sunflower field | 32% |
  | Harvested straw field with windrows | 60% |
  | Wet road edge | 140% |

  Each layer is cropped to the band it covers, so the Pi only blends the strips that matter.
- **The mirror** shows a flipped slice of the passing scenery, so its reflection streams by too.
- **The windshield sliver** collects drizzle dots that the wiper clears on each sweep (**Wiper speed**).
- **The fog** is a coarse density map over the side glass. A heavily blurred, whitened copy of the view is laid over the clear view, with the fog density as its transparency.
- **Weight:** fog grows back patchily (**Fog return time**) and creeps in from foggy neighbours (**Fog creep**). Droplets run down, catch for a moment, and leave clear trails that fog over again.

## Settings worth playing with

| Setting | Try |
|---|---|
| Driving speed | Crank it up to feel the layers separate; 0 to sit parked |
| Fog return time | 3 for glass that fogs right back; 40 for a lazy return |
| Fog creep | 0 for crisp drawn lines that just fade |
| Drizzle / Wiper speed | Heavier drizzle with a faster wiper for a proper shower |

## Ideas

- Sun breaking through: a slider from damp to bright summer (like the photo it's based on)
- A farm tractor or a cyclist overtaken on the road
- Writing with a fingertip leaves a faint ghost that reappears when the fog returns (like real glass)
