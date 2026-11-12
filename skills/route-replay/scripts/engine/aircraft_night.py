"""Opt-in aircraft-only cinematic lights, never measured lunar irradiance.

Pure deterministic preparation in camera coordinates; only Cycles consumes it.
"""
import math


def _smooth(a, b, x):
    t = min(1., max(0., (x-a)/(b-a)))
    return t*t*(3.-2.*t)


def cinematic_lights(sample):
    """Hashable key/fill directions and scene-relative RGB, with exact off/day zero."""
    strength = sample.get('aircraft_night_light', 0.)
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= 2:
        raise ValueError('aircraft_night_light must be finite in [0, 2]')
    sun = sample['sun_camera']
    night = 1.-_smooth(math.sin(math.radians(-12)), math.sin(math.radians(-2)), sun[2])
    fallback = (-.48, -.36, .8)  # Explicit camera-relative upper-side cinematic key.
    direction = fallback
    if strength and night:
        moon = sample.get('moon_camera', (0., 0., -1.))
        if len(moon) != 3 or not all(math.isfinite(v) for v in moon) or abs(sum(v*v for v in moon)-1.) > 1e-4:
            raise ValueError('cinematic lunar direction must be a finite unit vector')
        # Smoothly retain the dated direction only for a useful elevated Moon.
        # Flux is a *direction confidence*, not a physical scaling of this light.
        flux = max(sample.get('moon_rgb', (0., 0., 0.)))
        confidence = _smooth(0., .25, moon[2]) * _smooth(0., .001, flux)
        mixed = tuple((1.-confidence)*f + confidence*m for f,m in zip(fallback, moon))
        norm = math.sqrt(sum(v*v for v in mixed))
        direction = tuple(v/norm for v in mixed)
    gain = strength*night
    return (tuple(direction), tuple(gain*v for v in (.12, .14, .18)),
            (.6, .2, .7745966692414834), tuple(gain*v for v in (.025, .03, .04)))
