"""Projectile physics and difficulty curve."""
import random
import unittest

from gesture_slice import config
from gesture_slice.fruit import GameObject
from gesture_slice.game_engine import Game, level_for_score, settings_for_level


class PhysicsTests(unittest.TestCase):
    def test_gravity_pulls_down(self):
        obj = GameObject(0, 0, 0, -100, 10, gravity=1000)
        obj.update(0.1)
        self.assertGreater(obj.vy, -100)

    def test_launch_peaks_inside_screen_and_lands_back(self):
        game = Game(rng=random.Random(1))
        for _ in range(200):
            x, y, vx, vy, g = game.launch_parameters(40)
            obj = GameObject(x, y, vx, vy, 40, gravity=g)
            top = y
            for _ in range(2000):
                obj.update(1 / 120)
                top = min(top, obj.y)
                if obj.is_offscreen(game.width, game.height):
                    break
            self.assertGreater(top, 0, "fruit must not leave through the top")
            self.assertLess(top, game.height * 0.5, "fruit must rise high enough to slice")
            self.assertTrue(obj.is_offscreen(game.width, game.height))

    def test_levels_follow_thresholds(self):
        self.assertEqual(level_for_score(0), 1)
        self.assertEqual(level_for_score(149), 1)
        self.assertEqual(level_for_score(150), 2)
        self.assertEqual(level_for_score(400), 3)
        last = config.LEVEL_SCORE_THRESHOLDS[-1]
        self.assertEqual(level_for_score(last + config.LEVEL_STEP_AFTER), len(config.LEVEL_SCORE_THRESHOLDS) + 1)

    def test_difficulty_increases(self):
        s1, s2, s3, s6 = (settings_for_level(n) for n in (1, 2, 3, 6))
        self.assertLess(s1.speed, s2.speed)               # level 2: faster fruit
        self.assertGreater(s3.bomb_chance, s2.bomb_chance)  # level 3: more bombs
        self.assertLess(s6.spawn_interval, s3.spawn_interval)


if __name__ == "__main__":
    unittest.main()
