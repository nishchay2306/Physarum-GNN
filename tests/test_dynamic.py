"""Exercise the concurrent hazard producer and both moving routing agents."""
import unittest

from physrum.dynamic import Session, DEFAULT_START, DEFAULT_END


class DynamicTests(unittest.TestCase):
    def test_seeded_disruptions_and_arrival(self):
        simulation = Session(DEFAULT_START, DEFAULT_END, tick_seconds=0, max_ticks=150)
        simulation.run()
        state = simulation.get()
        self.assertTrue(state['done'])
        self.assertGreaterEqual(len(state['events']), 1)
        self.assertGreaterEqual(state['agents']['dijkstra']['metrics']['recalculations'], 1)
        self.assertTrue(all(agent['arrived'] for agent in state['agents'].values()))

    def test_invalid_endpoints(self):
        with self.assertRaises(ValueError):
            Session(DEFAULT_START, DEFAULT_START)


if __name__ == '__main__': unittest.main()
