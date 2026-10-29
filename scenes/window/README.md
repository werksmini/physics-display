# Foggy car window

![preview](preview.png)

**Landscape.** Riding in the passenger seat of a small classic 1970s sedan on a dreary San Francisco day. The side window is fogged up; wipe it with your finger to see out. The fog slowly comes back.

The layout follows a photo taken in a BMW 2002, turned to look out the passenger door:
- a sliver of windshield and black dash at the left, with an intermittent wiper clearing drizzle
- the slanted black A-pillar
- the front vent window with a chrome divider
- the big side window, with the B-pillar at the right
- a tan vinyl door panel with a chrome window crank and door pull
- a beige headliner with the sun visor overhead
- a rectangular chrome mirror outside at the front of the door

No badges or logos.

```bash
python run.py window            # Pi: hold the screen sideways (Flip landscape in the panel turns it the other way)
python run.py window --window   # laptop: opens a landscape window
```

## Touch

Swipe to wipe the condensation away: you're drawing on the window. Droplets gather at the edges of your wipes and run down the glass.

## How it works

- **Landscape:** the scene sets `LANDSCAPE = True`. The runner draws it at 640×480 and rotates it onto the portrait panel, and rotates your touches to match.
- **The street** is made of looping layers drawn once at startup, each scrolling at its own speed (parallax). The front of the car is to your left, so everything slides left to right. From far to near:
  - overcast sky with drifting fog banks
  - a hill of houses fading into the mist
  - rows of muted Victorian and Edwardian houses with bay windows, garages and front stairs, stepping up and down a hilly street
  - street trees and parked cars, on wet asphalt
- **Few landmarks on purpose:** just the feel of an ordinary SF street, with no bridge and no famous towers.
- **The windshield** shows the street ahead with lane markings rushing toward you. Drizzle dots build up on it until the wiper sweeps them away (**Wiper interval**).
- **The fog** is a coarse density map over the side glass. A heavily blurred, whitened copy of the view is laid over the clear view, with the fog density as its transparency.
- **Weight:** fog grows back patchily (**Fog return time**) and creeps in from foggy neighbours (**Fog creep**). Droplets run down, catch for a moment, and leave clear trails that fog over again.

## Settings worth playing with

| Setting | Try |
|---|---|
| Driving speed | 0 to sit parked |
| Fog return time | 3 for glass that fogs right back; 40 for a lazy return |
| Fog creep | 0 for crisp drawn lines that just fade |
| Drizzle / Wiper interval | Heavier drizzle with a faster wiper for a proper downpour |

## Ideas

- A cable car bell and a MUNI bus passing
- Streetlights flickering on as the afternoon darkens
- Writing with a fingertip leaves a faint ghost that reappears when the fog returns (like real glass)
