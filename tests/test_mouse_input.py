"""Mouse / trackpad movement -> cut segments and blade speed."""
import unittest

from gesture_slice.mouse_input import MotionTracker, MouseDetector


class MotionTrackerTests(unittest.TestCase):
    def test_first_point_has_no_segment(self):
        self.assertIsNone(MotionTracker().update(100, 100, 0.0))

    def test_fast_swipe_creates_segment_with_speed(self):
        m = MotionTracker()
        m.update(100, 300, 0.0)
        seg = m.update(400, 300, 0.1)            # 300 px in 0.1 s
        self.assertEqual(seg[:4], (100, 300, 400, 300))
        self.assertAlmostEqual(seg[4], 3000)

    def test_long_pause_breaks_the_line(self):
        m = MotionTracker(max_gap=0.25)
        m.update(0, 0, 0.0)
        self.assertIsNone(m.update(500, 500, 1.0))   # no giant jump-cut after a pause
        self.assertEqual(m.speed, 0.0)

    def test_reset_forgets_previous_point(self):
        m = MotionTracker()
        m.update(0, 0, 0.0)
        m.reset()
        self.assertIsNone(m.update(10, 10, 0.01))


class MouseDetectorTests(unittest.TestCase):
    def test_reports_position_and_presence(self):
        d = MouseDetector()
        self.assertFalse(d.last.present)
        frame = d.update(120, 80, 0.0)
        self.assertTrue(frame.present)
        self.assertEqual((frame.x, frame.y), (120, 80))

    def test_segment_after_second_movement(self):
        d = MouseDetector()
        d.update(0, 0, 0.0)
        frame = d.update(60, 80, 0.05)          # 100 px in 0.05 s
        self.assertAlmostEqual(frame.segment[4], 2000)


if __name__ == "__main__":
    unittest.main()
