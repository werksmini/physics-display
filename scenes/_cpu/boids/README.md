# Flocking birds

![preview](preview.png)

A flock of birds wheeling over a dusk sky. No bird leads; flocking emerges from three local rules (Craig Reynolds' *boids*, 1986).

```bash
python run.py boids            # Pi
python run.py boids --window   # laptop
```

## Touch

By default your finger is a **hawk**: the flock scatters away from it, then regroups. Set **Touch mode** to 1 and your finger becomes **food** the flock swarms toward.

## How it works

Every bird looks at the neighbours within its **Visual range** and steers by:

1. **Separation:** away from birds closer than **Personal space**
2. **Alignment:** toward the average heading of its neighbours
3. **Cohesion:** toward the centre of its neighbours

Birds also turn back inside an **Edge margin** and keep their speed between a minimum and a maximum. Every pair of birds is compared each step with NumPy, all at once. Birds are drawn as flapping chevrons; faster birds flap faster.

## Settings worth playing with

| Setting | Try |
|---|---|
| Cohesion high, alignment low | Tight swirling balls, like a bait ball of fish |
| Alignment high, cohesion low | Long ribbons all flying the same way |
| Visual range small | Many small flocks |
| Separation 0 | Birds pile on top of each other |

## Ideas

- A single predator bird that hunts on its own
- Wind that pushes the flock
- Starling murmuration at sunset, with a few hundred more birds (needs a speed pass)
