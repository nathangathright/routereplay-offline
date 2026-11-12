"""Portable cinematic source boundaries; no Blender or downloaded assets."""
import sys
from pathlib import Path
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/route-replay/scripts/engine'))
sys.path.insert(0,str(ROOT/'skills/route-replay/scripts'))
from aircraft_night import cinematic_lights
from trip import load_trip, TripError
from radiometry import TransportLayer

class AircraftNightTests(unittest.TestCase):
    def sample(self, **kw):
        return dict(sun_camera=(0.,0.,-1.), moon_camera=(.6,0.,.8),moon_rgb=(.01,.01,.01),aircraft_night_light=1.,**kw)

    def test_default_and_day_have_exactly_zero_source(self):
        for sample in ({'sun_camera':(0,0,-1)}, {'sun_camera':(0,0,1),'aircraft_night_light':2}):
            state=cinematic_lights(sample)
            self.assertEqual(state[1],(0.,0.,0.));self.assertEqual(state[3],(0.,0.,0.))
        day={'sun_camera':(0.,0.,.8)}
        self.assertEqual(cinematic_lights(day),cinematic_lights(dict(day,aircraft_night_light=2.)))

    def test_usable_moon_and_dark_fallback(self):
        s=self.sample();self.assertEqual(cinematic_lights(s)[0],s['moon_camera'])
        for moon,rgb in (((0,0,-1),(.01,)*3),((.6,0,.8),(0,)*3)):
            s.update(moon_camera=moon,moon_rgb=rgb)
            np.testing.assert_allclose(cinematic_lights(s)[0],(-.48,-.36,.8))
            self.assertGreater(min(cinematic_lights(s)[1]),0)

    def test_bounded_gain_smooth_twilight_and_determinism(self):
        s=self.sample();states=[]
        for z in np.linspace(-.21,0,300):
            s['sun_camera']=(0,0,float(z));states.append(cinematic_lights(s)[1][0])
        self.assertTrue(np.all(np.diff(states)<=0));self.assertLess(max(abs(np.diff(states))),.002)
        self.assertEqual(cinematic_lights(s),cinematic_lights(s))
        for bad in (-1,3,float('nan'),True):
            s['aircraft_night_light']=bad
            with self.assertRaises(ValueError):cinematic_lights(s)

    def test_foreground_transport_still_attenuates_added_light(self):
        s=self.sample();rgb=np.array(cinematic_lights(s)[1],np.float32).reshape(1,1,3)
        air=TransportLayer(np.zeros((1,1,3),np.float32),np.full((1,1,3),.3,np.float32))
        cloud=TransportLayer(np.zeros((1,1,3),np.float32),np.zeros((1,1,3),np.float32))
        np.testing.assert_allclose(air.over(rgb),rgb*.3)
        np.testing.assert_array_equal(cloud.over(rgb),0)

    def test_trip_style_enters_identity_and_is_bounded(self):
        import json,tempfile
        sample=json.loads((ROOT/'skills/route-replay/examples/sample-single-leg.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trip.json';p.write_text(json.dumps(sample));off=load_trip(p)
            sample.setdefault('style',{})['aircraft_night_light']=1;p.write_text(json.dumps(sample));on=load_trip(p)
            self.assertNotEqual(off.to_dict(),on.to_dict())
            for bad in (-1,2.1,True):
                sample['style']['aircraft_night_light']=bad;p.write_text(json.dumps(sample))
                with self.assertRaises(TripError):load_trip(p)

if __name__=='__main__':unittest.main()
