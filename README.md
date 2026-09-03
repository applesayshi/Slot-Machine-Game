# Slot Machine (Lucky 7)

A three-reel slot machine in Python, with two front-ends sharing one set of rules.

| File | What it is |
| --- | --- |
| `slot_core.py` | The rules: symbol counts, payouts, the spin, and the win check. |
| `slot_machine.py` | The functions/information of the game. Also includes the main function.  |
| `slot_machine_gui.py` | A drawn cabinet with colour, fruit symbols and reels that spin. |

Both front-ends import `slot_core`, so the odds and payouts can never drift apart.

## Running it

```bash
python3 slot_machine.py            # the console version, no dependencies

pip install -r requirements.txt    # pygame, for the graphical version
python3 slot_machine_gui.py
```

## Playing

Insert an amount, pick how many lines to bet on and how much to stake on each
one, then pull the lever. A line pays when all three reels show the same symbol
on it. Lines are counted from the top: 1 line means the top row, 2 the top two,
3 all of them.

| Symbol | Per reel | Pays |
| --- | --- | --- |
| Seven | 2 | 7 × bet per line |
| Bell | 4 | 6 × bet per line |
| Cherry | 6 | 5 × bet per line |
| Lemon | 8 | 4 × bet per line |

Rarer symbols pay more: each reel is filled from the same pool of 20 symbols, so
a seven turns up far less often than a lemon.

## Controls (graphical version)

| Key | Action |
| --- | --- |
| `SPACE` / `ENTER` | Spin (or click **SPIN**, or the lever) |
| `UP` / `DOWN` | Change the number of lines |
| `LEFT` / `RIGHT` | Change the bet per line (hold `SHIFT` for ±10) |
| `M` | Mute |
| `Q` / `ESC` | Cash out |

The buttons on the control deck do the same things if you would rather click.

