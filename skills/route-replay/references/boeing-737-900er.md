# Boeing 737-900ER dimensional illustration

Select `737-900er` in a trip. This builds an independent original 737NG mesh, not the A321neo mesh or a uniform rescale. It depicts conventional upward blended winglets and CFM56-7B-family nacelles in flight configuration, without landing gear or an airline livery. Type selection does not establish a registration, live assignment, or a particular aircraft's winglet retrofit. Split-scimitar and MAX winglets are not claimed.

## Sources checked

- Boeing, *737 Airplane Characteristics for Airport Planning*, D6-58325-7, Rev C, October 2025, section 2.2.8, page 2-16 (PDF page 37): https://www.boeing.com/content/dam/boeing/v2/airports/acaps/737NG_REV_C.pdf
- Aviation Partners Boeing, 737-900ER blended-winglet configuration: https://www.aviationpartnersboeing.com/products_737_900er.php
- CFM International, CFM56 family: https://www.cfmaeroengines.com/cfm56/CFM56-5B-CFM56-7B

The Boeing three-view was visually inspected on 2026-11-07. Its dimensioned anchors are overall length 42.11 m, winglet span 35.79 m, body width 3.76 m, tailplane span 14.35 m, engine centre offset 4.83 m, inlet station 14.73 m aft of nose, and tip aft stations 25.45 m (approximate) / 27.58 m. The 5.72 m callout is main-gear track, not engine spacing.

The 42.11 m overall envelope ends at the horizontal stabilizer, behind the pressure fuselage/APU. The illustrative fuselage ends at 40.90 m; validation checks its separate body envelope and the 42.11 m nose-to-stabilizer envelope. The total envelope, rather than the fuselage midpoint, is centered in the shared 12.01-unit display frame.

## Modeled detail and limitations

Planform and body stations live in `scripts/aircraft_assets.py`. Local wing sections, nose, cockpit glazing, body height, aft fuselage, dihedral, dorsal fin, nacelle shape and inlet depth are approximate samples from the three-view, not CAD or certified dimensions. The flattened CFM56 cowling, recessed fan, smooth exhaust, broad root chord, tapered swept wing, upward blended tips, six windscreen panes and long dorsal fin distinguish this silhouette from an Airbus or 737 MAX. No specific engine thrust rating is asserted. Ordinary shared modeled flex and dated lighting still apply.

`tests/test_boeing_737.py` checks dimensions, left/right symmetry, planform anchors, configuration honesty and trip selection. Blender `--737-900er --validate-only` checks actual mesh dimensions (0.0001 m control-mesh tolerance), the independent engine geometry and pose/flex path. Subdivision and bevels slightly soften the rendered surface relative to its control mesh, so this tolerance is not a claim of engineering accuracy.
