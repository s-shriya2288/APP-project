# Assets

Gesture Slice needs **no image or sound files** – every fruit, bomb, button,
icon and sound effect is generated in code at start-up
(`gesture_slice/sprites.py` and `gesture_slice/sound.py`).

## Optional: use your own fruit art

Put a square PNG with a transparent background in `assets/images/` named
after the fruit:

```
assets/images/apple.png
assets/images/orange.png
assets/images/lime.png
assets/images/watermelon.png
assets/images/plum.png
assets/images/peach.png
assets/images/golden star.png
```

The game scales it to the right size and uses it instead of the generated
fruit (the sliced halves are cut from your image). Missing or unreadable files
are ignored, and the game shows a short warning and keeps the generated art.
