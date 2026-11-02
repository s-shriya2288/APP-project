"""Collision detection: blade segment vs. fruit circle."""
import unittest

from gesture_slice.fruit import (Bomb, Fruit, FRUIT_BY_NAME, distance_point_to_segment,
                                 segment_intersects_circle)


class CollisionTests(unittest.TestCase):
    def test_segment_through_centre_hits(self):
        self.assertTrue(segment_intersects_circle(0, 0, 100, 0, 50, 0, 10))

    def test_segment_just_touching_edge_hits(self):
        self.assertTrue(segment_intersects_circle(0, 0, 100, 0, 50, 10, 10))

    def test_segment_passing_above_misses(self):
        self.assertFalse(segment_intersects_circle(0, 0, 100, 0, 50, 10.5, 10))

    def test_segment_ending_before_circle_misses(self):
        # The infinite line would hit, but the segment stops short.
        self.assertFalse(segment_intersects_circle(0, 0, 30, 0, 50, 0, 10))

    def test_zero_length_segment(self):
        self.assertEqual(distance_point_to_segment(3, 4, 0, 0, 0, 0), 5)

    def test_fruit_slice_returns_two_halves_moving_apart(self):
        fruit = Fruit(FRUIT_BY_NAME["apple"], 200, 200, 0, -300)
        top, bottom = fruit.slice(0)          # horizontal swipe
        self.assertTrue(fruit.sliced)
        self.assertFalse(fruit.alive)
        self.assertLess(top.vy, bottom.vy)    # one half goes up, the other down
        self.assertAlmostEqual((top.angle - bottom.angle) % 360, 180)

    def test_bomb_fuse_rotates_with_bomb(self):
        bomb = Bomb(0, 0, 0, 0)
        bomb.angle = 0
        x0, y0 = bomb.fuse_tip()
        bomb.angle = 180
        x1, y1 = bomb.fuse_tip()
        self.assertAlmostEqual(x0, -x1, places=6)
        self.assertAlmostEqual(y0, -y1, places=6)


if __name__ == "__main__":
    unittest.main()
