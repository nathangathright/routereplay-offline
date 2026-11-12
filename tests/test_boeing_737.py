"""737-900ER manufacturer envelope and independent silhouette regressions."""
import ast
from pathlib import Path
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'skills/route-replay/scripts'
sys.path.insert(0,str(SCRIPTS))
from aircraft_assets import (BOEING_737_900ER as SPEC, BOEING_737_PLANFORM as PLAN,
                             BOEING_737_BODY as BODY, boeing_737_model_point as point)
from trip import SUPPORTED_AIRCRAFT, trip_from_dict, load_trip


class Boeing737Tests(unittest.TestCase):
    def test_all_entry_points_share_the_supported_type_registry(self):
        from aircraft_assets import AIRCRAFT_LENGTHS_M, SUPPORTED_AIRCRAFT as supported
        from calibration import TYPES
        self.assertEqual(SUPPORTED_AIRCRAFT,supported)
        self.assertEqual(TYPES,{'generic',*supported})
        self.assertEqual(set(AIRCRAFT_LENGTHS_M),set(supported))
        tree=ast.parse((SCRIPTS/'engine/aircraft_blender.py').read_text())
        spec_node=next(n for n in tree.body if isinstance(n,ast.Assign)
                       and any(isinstance(t,ast.Name) and t.id=='AIRFRAME_SPECS' for t in n.targets))
        specs=eval(compile(ast.Expression(spec_node.value),'<specs>','eval'),{'BOEING_737_900ER':SPEC})
        self.assertEqual({name:value['length_m'] for name,value in specs.items()},AIRCRAFT_LENGTHS_M)
        variant=next(n for n in tree.body if isinstance(n,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id=='VARIANT' for t in n.targets))
        self.assertIn('SUPPORTED_AIRCRAFT',ast.unparse(variant))

    def test_manufacturer_envelope_and_centered_display(self):
        self.assertEqual((SPEC['length_m'],SPEC['span_m'],SPEC['fuselage_width_m'],
                          SPEC['tailplane_span_m']), (42.11,35.79,3.76,14.35))
        self.assertAlmostEqual(max(p[0] for p in PLAN['winglet'])*2,SPEC['span_m'])
        self.assertAlmostEqual(max(p[0] for p in PLAN['tailplane'])*2,14.35)
        self.assertAlmostEqual(max(p[1] for p in BODY)*2,3.76)
        nose=point((0,0,0));tail=point((0,42.11,0))
        self.assertAlmostEqual(nose[1]-tail[1],12.01)
        self.assertAlmostEqual(nose[1]+tail[1],0)
        self.assertLess(BODY[-1][0],42.11)  # stabilizer, not APU, ends envelope

    def test_independent_ng_planform_and_upswept_blended_tips(self):
        wing=PLAN['wing'];tip=PLAN['winglet']
        self.assertEqual(wing[0][:2],(1.70,16.50))
        self.assertEqual(wing[-1][:2],(1.70,23.05))
        self.assertAlmostEqual(max(p[0] for p in wing),17.05)
        self.assertEqual(max(p[1] for p in tip),27.58)
        self.assertGreater(max(p[2] for p in tip)-min(p[2] for p in tip),3.)
        self.assertGreater(min(p[2] for p in tip),0)  # no scimitar lower blade
        # Swept NG wing with a substantial root chord, not a scaled A321 wing.
        area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(wing,wing[1:]+wing[:1])))
        self.assertGreater(area,85.)
        self.assertLess(area,125.)
        self.assertEqual(PLAN['fin'][0],(0.,31.60,1.90))  # long dorsal fillet
        for outline in PLAN.values():
            for p in outline:
                left,right=point(p,-1),point(p,1)
                self.assertAlmostEqual(left[0],-right[0])
                self.assertEqual(left[1:],right[1:])

    def test_737_selection_reaches_dedicated_builder(self):
        self.assertIn('737-900er',SUPPORTED_AIRCRAFT)
        tree=ast.parse((SCRIPTS/'engine/aircraft_blender.py').read_text())
        builder=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_boeing_737')
        self.assertNotIn('adapt_airframe',ast.unparse(builder))
        selector=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_procedural_aircraft')
        branch=next(n for n in selector.body if isinstance(n,ast.If) and "737-900er" in ast.unparse(n.test))
        self.assertIn('create_boeing_737',ast.unparse(branch))
        self.assertIsInstance(branch.body[-1],ast.Return)
        self.assertIn('CFM56 rounded engine nacelle',ast.unparse(builder))
        self.assertNotIn('chevron_cowl(',ast.unparse(builder))
        # Parsing must retain the user's exact type rather than substituting A321.
        import json
        example=next((SCRIPTS.parent/'examples').glob('*.json'))
        data=json.loads(example.read_text())
        for flight in data['flights']: flight['aircraft']='737-900er'
        trip=trip_from_dict(data)
        self.assertTrue(all(leg.aircraft=='737-900er' for leg in trip.legs))

    def test_manufacturer_intake_placement_and_honest_configuration(self):
        self.assertEqual(SPEC['engine_center_offset_m'],4.83)
        self.assertEqual(SPEC['engine_lip_aft_nose_m'],14.73)
        self.assertIn('not verification',SPEC['equipment_evidence'])
        self.assertIn('approximate',SPEC['geometry_notes'])
        self.assertIsNone(SPEC['registration'])


if __name__=='__main__': unittest.main()
