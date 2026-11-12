"""Fleet capacity and dynamic disruption integration checks."""
import unittest
import statistics

from physrum.fleet import Fleet, DEPOTS, ZONES, bpr_multiplier
from physrum.dynamic import GRAPH, DEFAULT_START, DEFAULT_END


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
            free_flow = sum(GRAPH.minutes(edge)
                            for truck in result['fleets'][name]['trucks']
                            for edge in truck['traversed'])
            self.assertGreater(metrics['travel_min'], free_flow)
            self.assertAlmostEqual(metrics['travel_min'] - free_flow,
                                   metrics['congestion_extra_min'], delta=.003)
            arrivals = [truck['arrival_tick'] for truck in result['fleets'][name]['trucks']]
            series = result['fleets'][name]['arrival_series']
            self.assertEqual(metrics['median_arrival_tick'], statistics.median(arrivals))
            self.assertEqual(series[0], [0, 0])
            self.assertEqual(len(series), result['tick']+1)
            self.assertEqual(series[-1], [result['tick'], metrics['delivered']])
            self.assertTrue(all(a[1] <= b[1] for a, b in zip(series, series[1:])))
        self.assertGreater(result['fleets']['dijkstra']['metrics']['recalculations'], 0)

    def test_unfinished_fleet_does_not_claim_a_median(self):
        fleet = Fleet(count=2, tick_seconds=0, max_ticks=1)
        fleet.run()
        for output in fleet.get()['fleets'].values():
            self.assertEqual(output['arrival_series'], [[0, 0], [1, 0]])
            self.assertIsNone(output['metrics']['median_arrival_tick'])

    def test_entered_count_bounds(self):
        self.assertEqual(Fleet(count=1).count, 1)
        self.assertEqual(Fleet(count=1000).count, 1000)
        for invalid in (0, 1001):
            with self.assertRaises(ValueError): Fleet(count=invalid)

    def test_congestion_increases_time_for_both_policies(self):
        self.assertAlmostEqual(bpr_multiplier(8, 8), 1.30)
        self.assertAlmostEqual(bpr_multiplier(16, 8), 5.80)

    def test_simulated_junction_links_offer_real_alternates(self):
        links = [edge for edge in GRAPH.edges if edge.get('simulated')]
        self.assertGreaterEqual(len(links), 100)
        for edge in links[:5]:
            self.assertTrue(GRAPH.dijkstra(edge['u'], edge['v'], {edge['id']}))

    def test_default_route_has_similar_length_detours(self):
        route = GRAPH.dijkstra(DEFAULT_START, DEFAULT_END)
        free_flow = GRAPH.drive_time(route)
        synthetic = {edge['id'] for edge in GRAPH.edges if edge.get('simulated')}
        def close_to_original(extra_blocked):
            count = 0
            for edge in route[2:-2]:
                detour = GRAPH.dijkstra(DEFAULT_START, DEFAULT_END,
                                        extra_blocked | {edge})
                count += bool(detour and GRAPH.drive_time(detour) <= 1.25*free_flow)
            return count
        self.assertGreaterEqual(close_to_original(set()), 10)
        self.assertGreater(close_to_original(set()), close_to_original(synthetic))

    def test_selected_route_changes_real_fleet_endpoints(self):
        fleet = Fleet(count=4, start=DEPOTS[1], target=ZONES[1])
        self.assertEqual(fleet.depots[0], DEPOTS[1])
        self.assertEqual(fleet.zones[0], ZONES[1])
        self.assertEqual(fleet.trucks['dijkstra'][0]['node'], DEPOTS[1])
        self.assertEqual(fleet.trucks['dijkstra'][0]['target'], ZONES[1])


if __name__ == '__main__': unittest.main()
