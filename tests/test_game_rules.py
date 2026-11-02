"""Scoring, combos, bombs, lives, timer and pause."""
import random
import unittest

from gesture_slice import config
from gesture_slice.fruit import Bomb, Fruit, FRUIT_BY_NAME
from gesture_slice.game_engine import (BombHit, ComboScored, FruitSliced, Game, GameOver)

FAST = 5000.0


def playing_game():
    game = Game(rng=random.Random(3))
    game.state = Game.PLAYING
    game.spawn_timer = 999          # no random spawns during the test
    return game


def swipe(y, x0=0, x1=1100):
    return [(x0, y, x1, y, FAST)]


class GameRuleTests(unittest.TestCase):
    def test_countdown_then_playing(self):
        game = Game()
        for _ in range(int(config.COUNTDOWN_SECONDS * 60) + 2):
            game.update(1 / 60)
        self.assertEqual(game.state, Game.PLAYING)

    def test_slicing_scores_points(self):
        game = playing_game()
        game.fruits.append(Fruit(FRUIT_BY_NAME["apple"], 300, 300, 0, 0, gravity=0))
        events = game.update(1 / 60, swipe(300))
        self.assertEqual(game.stats.score, config.NORMAL_POINTS)
        self.assertEqual(game.stats.fruits_sliced, 1)
        self.assertTrue(any(isinstance(e, FruitSliced) for e in events))
        self.assertEqual(len(game.halves), 2)

    def test_special_fruit_worth_more(self):
        game = playing_game()
        game.fruits.append(Fruit(FRUIT_BY_NAME["golden star"], 300, 300, 0, 0, gravity=0))
        game.update(1 / 60, swipe(300))
        self.assertEqual(game.stats.score, config.SPECIAL_POINTS)

    def test_slow_movement_does_not_cut(self):
        game = playing_game()
        game.fruits.append(Fruit(FRUIT_BY_NAME["apple"], 300, 300, 0, 0, gravity=0))
        game.update(1 / 60, [(0, 300, 1100, 300, 10.0)])
        self.assertEqual(game.stats.fruits_sliced, 0)

    def test_combo_bonus(self):
        game = playing_game()
        for x in (200, 400, 600):
            game.fruits.append(Fruit(FRUIT_BY_NAME["apple"], x, 300, 0, 0, gravity=0))
        game.update(1 / 60, swipe(300))
        events = []
        for _ in range(30):
            events += game.update(1 / 60)
        combos = [e for e in events if isinstance(e, ComboScored)]
        self.assertEqual(len(combos), 1)
        self.assertEqual(combos[0].count, 3)
        self.assertEqual(game.stats.score, 3 * config.NORMAL_POINTS + 2 * config.COMBO_BONUS_PER_EXTRA_FRUIT)
        self.assertEqual(game.stats.max_combo, 3)

    def test_bomb_costs_life_and_three_bombs_end_game(self):
        game = playing_game()
        for i in range(config.START_LIVES):
            game.bombs.append(Bomb(500, 300, 0, 0, gravity=0))
            events = game.update(1 / 60, swipe(300))
            self.assertTrue(any(isinstance(e, BombHit) for e in events))
            game.invulnerable = 0
        self.assertEqual(game.lives, 0)
        self.assertEqual(game.state, Game.OVER)
        self.assertEqual(game.over_reason, "bombs")

    def test_timer_ends_game(self):
        game = playing_game()
        game.time_left = 0.01
        events = game.update(1 / 60)
        self.assertTrue(any(isinstance(e, GameOver) and e.reason == "time" for e in events))

    def test_missed_fruit_lowers_accuracy(self):
        game = playing_game()
        game.fruits.append(Fruit(FRUIT_BY_NAME["apple"], 300, game.height + 200, 0, 10))
        game.fruits.append(Fruit(FRUIT_BY_NAME["apple"], 300, 300, 0, 0, gravity=0))
        game.update(1 / 60, swipe(300))
        self.assertEqual(game.stats.fruits_missed, 1)
        self.assertEqual(game.stats.accuracy, 50.0)

    def test_pause_freezes_everything(self):
        game = playing_game()
        fruit = Fruit(FRUIT_BY_NAME["apple"], 300, 300, 0, -200)
        game.fruits.append(fruit)
        game.pause()
        t = game.time_left
        game.update(0.5, swipe(300))
        self.assertEqual((fruit.y, game.time_left, game.stats.score), (300, t, 0))
        game.resume()
        self.assertEqual(game.state, Game.PLAYING)

    def test_long_random_game_never_crashes(self):
        rng = random.Random(42)
        game = Game(round_seconds=120, rng=random.Random(7))
        for _ in range(60 * 130):
            segs = [(rng.uniform(0, 1100), rng.uniform(0, 700), rng.uniform(0, 1100), rng.uniform(0, 700),
                     rng.uniform(0, 3000)) for _ in range(rng.randint(0, 2))]
            game.update(1 / 60, segs)
            self.assertLessEqual(len(game.fruits) + len(game.bombs), config.MAX_ACTIVE_OBJECTS)
            if game.state == Game.OVER:
                break
        self.assertEqual(game.state, Game.OVER)


if __name__ == "__main__":
    unittest.main()
