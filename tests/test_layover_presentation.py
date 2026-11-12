"""Continuous physical/weather clocks and fixed HUD placement during a stop."""
from pathlib import Path
import sys
import unittest
import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]/'skills/route-replay/scripts'
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS/'engine')]
from trip import trip_from_dict
from motion import Motion
from labels import Labels
from frame_context import context_at


def synthetic_trip():
    return trip_from_dict({
        'schema_version': 1, 'title': 'Synthetic Pacific stop clock regression',
        'airports': {
            'AAA': {'name':'Origin', 'lat':-37.67, 'lon':144.84, 'timezone':'UTC'},
            'BBB': {'name':'Connection', 'lat':37.62, 'lon':-122.38, 'timezone':'UTC'},
            'CCC': {'name':'Destination', 'lat':41.97, 'lon':-87.91, 'timezone':'UTC'}},
        'flights': [
            {'from':'AAA','to':'BBB','departure':'2031-06-01T00:00:00+00:00',
             'arrival':'2031-06-01T14:00:00+00:00','aircraft':'787-9'},
            {'from':'BBB','to':'CCC','departure':'2031-06-01T20:00:00+00:00',
             'arrival':'2031-06-02T00:00:00+00:00','aircraft':'a321neo'}],
        'video': {'duration_s':20,'fps':24,'departure_hold_s':1.5,
                  'arrival_hold_s':2,'layover_hold_s':4},
        'weather': {'mode':'forecast'}})


class LayoverPresentationTests(unittest.TestCase):
    def test_every_layover_frame_advances_sun_and_weather_without_moving_camera(self):
        trip=synthetic_trip(); motion=Motion(trip)
        start,end=trip.leg_intervals[0][1],trip.leg_intervals[1][0]
        times=[i/trip.fps for i in range(trip.frame_count) if start<i/trip.fps<end]
        frames=[context_at(motion,t) for t in times]
        self.assertGreater(len(frames),90)
        for a,b in zip(frames,frames[1:]):
            self.assertLess(a.physical_utc,b.physical_utc)
            self.assertLess(a.weather_utc,b.weather_utc)
            self.assertEqual(a.physical_utc,a.weather_utc)
            self.assertGreater(np.linalg.norm(np.subtract(a.sun_world,b.sun_world)),0)
            np.testing.assert_allclose(a.camera_basis,b.camera_basis,atol=1e-12)
            self.assertEqual(a.globe_radius_px,b.globe_radius_px)
            self.assertAlmostEqual(a.aircraft_altitude_m,0,places=8)
        self.assertEqual(trip.travel_time(start),trip.legs[0].arrive)
        self.assertEqual(trip.travel_time(end),trip.legs[1].depart)
        self.assertGreater(np.linalg.norm(np.subtract(frames[0].sun_world,frames[-1].sun_world)),1)
        self.assertEqual([f.to_dict() for f in frames],
                         [context_at(motion,t).to_dict() for t in reversed(times)][::-1])

    def test_stop_code_stays_fixed_future_code_waits_and_departed_code_recedes(self):
        trip=synthetic_trip(); motion=Motion(trip); labels=Labels(motion)
        arrival,departure=trip.leg_intervals[0][1],trip.leg_intervals[1][0]
        states=[labels.state(1,float(t)) for t in np.linspace(arrival,departure,25)]
        self.assertTrue(all(state==states[0] for state in states))
        self.assertTrue(all(labels.active(1,float(t)) for t in np.linspace(arrival,departure,25)))
        self.assertFalse(any(labels.active(2,float(t)) for t in np.linspace(0,departure-1e-6,100)))
        later=labels.state(1,departure+.5)
        self.assertLess(later[2],states[0][2])
        x,y,w,h,alpha=states[0]
        self.assertFalse(x<652 and x+w>428 and y<1072 and y+h>848)
        self.assertGreater(alpha,0)
        self.assertFalse((trip.telemetry or {}).get('enabled',False))
        self.assertEqual(trip.moments,())


if __name__=='__main__': unittest.main()
