# Barley field

![preview](preview.png)

A barley field in the wind, seen from eye level, based on a photo taken in France: soft blue sky with fair-weather clouds, a field going hazy and golden toward the horizon and greener up close, long bristly awns, and tall green wild grasses in front with drooping spikelets and purple flower spikes.

Run your finger through the field like a hand.

```bash
python run.py tallgrass            # Pi
python run.py tallgrass --window   # laptop
```

## Touch

Touch and drag through the barley. Stalks and grasses near your finger are pushed aside, and dragging sweeps them along. Hold still and a gap opens. Let go and they spring back.

## How it works

- **Backdrop (drawn once):** sky gradient; the distant field painted with thousands of slanted awn strokes, with the far third blurred slightly for depth of field.
- **Clouds:** soft shapes made by drawing puffs and then blurring them, drifting slowly.
- **Wind waves:** a noise field drifts across the far field and brightens it in bands that widen toward you, like gusts combing the barley.
- **Barley stalks:** each tip is a 2D spring on the ground plane, projected for a low camera (**View angle**). Heads nod downwind under their weight (**Head weight**).
- **Detail by distance:** far stalks are just a head (the painted field fills in the rest); mid stalks add a stem and a couple of awns; near stalks get braided, shaded heads and more awns. This keeps it fast on the Pi.
- **Foreground:** tall green blades, spikelet stems and purple spikes, each a bending spring that the wind and your hand both push.

## Settings worth playing with

| Setting | Try |
|---|---|
| Wind waves | Up to 1.5–2 for strong rolling sheen across the field |
| Gust size / speed | Large and slow, like the photo's broad combed patches |
| Head weight | High for heavy, deeply nodding barley |
| View angle | 5 for crouching in the field; 35+ for looking down into it |
| Horizon height | Lower for more field; higher for more sky |

## Ideas

- Golden-hour palette with long warm light
- A swallow or two skimming over the field
- Seeds that shake loose when you brush hard
