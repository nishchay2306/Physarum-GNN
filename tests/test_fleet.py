"""Fleet capacity and dynamic disruption integration checks."""
import unittest

from physrum.fleet import Fleet, DEPOTS, ZONES


class FleetTests(unittest.TestCase):
    def test_seeded_fleet_competes_on_same_hazards(self):
        fleet = Fleet(count=20, tick_seconds=0, max_ticks=350)
        fleet.run()
        result = fleet.get()
        self.assertTrue(result['events'])
        for name in ('dijkstra', 'physarum'):
            metrics = result['fleets'][name]['metrics']
            self.assertEqual(metrics['delivered'], 20)
            self.assertGreater(metrics['congestion_wait_ticks'], 0)
            self.assertEqual(len(result['fleets'][name]['trucks']), 20)
        self.assertGreater(result['fleets']['dijkstra']['metrics']['recalculations'], 0)

    def test_entered_count_bounds(self):
        self.assertEqual(Fleet(count=1).count, 1)
        self.assertEqual(Fleet(count=120).count, 120)
        for invalid in (0, 121):
            with self.assertRaises(ValueError): Fleet(count=invalid)

    def test_selected_route_changes_real_fleet_endpoints(self):
        fleet = Fleet(count=4, start=DEPOTS[1], target=ZONES[1])
        self.assertEqual(fleet.depots[0], DEPOTS[1])
        self.assertEqual(fleet.zones[0], ZONES[1])
        self.assertEqual(fleet.trucks['dijkstra'][0]['node'], DEPOTS[1])
        self.assertEqual(fleet.trucks['dijkstra'][0]['target'], ZONES[1])


if __name__ == '__main__': unittest.main()
