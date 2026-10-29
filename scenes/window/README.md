# Foggy car window

![preview](preview.png)

Riding in the passenger seat of a small classic 1970s sedan down a rural Midwest road at blue hour. The big side window is fogged up; wipe it with your finger to see out. The fog slowly comes back.

The car is styled after the BMW 2002 era: a wide, airy greenhouse with thin pillars, bright chrome trim, a front vent window, a small round chrome mirror, and a pleated cognac vinyl door with a chrome window crank. No badges or logos.

```bash
python run.py window            # Pi
python run.py window --window   # laptop
```

## Touch

Swipe to wipe the condensation away: you're drawing on the window. Through the clear patches you see the fields sliding past and the round chrome mirror outside the vent window. Droplets gather at the edges of your wipes and run down the glass.

## How it works

- **The view is wide-angle:** the glass fills about 70% of the screen.
- **The land** is made of looping layers drawn once at startup, each scrolling at its own speed (parallax). The car's front is to your left, so everything slides left to right. From far to near:
  - **Horizon:** tree lines, farmsteads with a lit window and a glowing yard light, silos and a water tower.
  - **Fields:** round hay bales scattered through them.
  - **Telephone poles:** their wires sag between poles and appear to rise and fall as they pass.
  - **Fence posts and roadside grass:** the nearest and fastest layers.
- **The sky:** blue hour, with a few early stars and a thin moon.
- **The round chrome mirror** is outside the glass, so it's under the fog too.
- **The fog** is a coarse density map over the glass. Each frame, a heavily blurred, brightened copy of the view is laid over the clear view, with the fog density as its transparency. Under thick fog you only see glowing blobs of light.
- **Weight:**
  - Fog grows back patchily, faster in some spots than others (**Fog return time**), and creeps in from foggy neighbours (**Fog creep**), so wipe edges soften and close in.
  - Droplets run down, catch on the glass for a moment, then carry on, cutting thin clear trails that fog over again.

## Settings worth playing with

| Setting | Try |
|---|---|
| Driving speed | 0 to pull over on the shoulder |
| Fog return time | 3 for a cold night where it fogs right back; 40 for a lazy return |
| Fog creep | 0 for crisp drawn lines that just fade; 2+ for edges that close in |
| Drips from wipes / Random drips | Up for a wetter window |
| Fog brightness | Higher for milky, glowing fog |

## Ideas

- Time slider: dusk deepening into night, with fireflies over the fields
- Rain on the outside of the glass, with drops streaking sideways at speed
- An oncoming car's headlights sweeping the interior
- Writing with a fingertip leaves a faint ghost that reappears when the fog returns (like real glass)
