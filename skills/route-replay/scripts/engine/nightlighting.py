"""Historical city-light sources in scene-relative linear RGB.

The 2016 grayscale Black Marble image locates aggregate emission, not measured
CCT, fixture types, switching times or contemporary land use. The regional
mixtures and mean-solar-time schedules are modeled priors. Physical UTC selects
immutable causal photocell state; weather UTC is used only in its prepass.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from runtime import ASSETS
from citylight_model import activation_components
from citypopulations import (geographic_fields, regional_populations, population_colors,
                             schedule_fractions, unit_points, utc_timestamp)
from causal_lights import LampTimeline, build_lamp_timeline
# Artistic scene-relative emitted luminance at the brightest source pixel.
# Directly sunlit diffuse white is approximately one in the shared HDR scene.
EMISSION_LUMINANCE = .45


@lru_cache(maxsize=1)
def light_texture():
    """A single scalar texture, cached once per rendering worker."""
    return np.asarray(Image.open(ASSETS / 'nightlights' /
                     'BlackMarble_2016_gray_8192.png').convert('L'))


@lru_cache(maxsize=1)
def _lighting_profile():
    import runtime
    from lighting_profile import read_profile
    record = getattr(runtime, 'BUNDLE', {}).get('lighting_profile')
    return read_profile(ASSETS / record['path']) if record else None


@lru_cache(maxsize=1)
def _timeline():
    from runtime import WORK
    directory = WORK / 'city-lights'
    if not (directory / 'metadata.json').is_file():
        raise RuntimeError('Prepare chronological city-light state before rendering frames.')
    return LampTimeline.load(directory)


def prepare_city_lights(trip, work, physical_times=None):
    """Build once before workers; supply all exact requested physical UTCs.

    Cache files are immutable per content-addressed render work directory.
    Only requested samples are retained, so long layovers do not allocate one
    global light map per elapsed five minutes. Sparse gaps receive fresh warmup.
    """
    from datetime import datetime, timedelta, timezone
    import json
    from astronomy import sun_direction
    from trip import WEATHER_HOLD_MINUTES
    directory = Path(work) / 'city-lights'
    times = (list(physical_times) if physical_times is not None else
             [trip.travel_time(i / trip.fps) for i in range(trip.frame_count)] +
             [trip.travel_time(trip.duration_s)])
    stamps = np.unique([utc_timestamp(dt) for dt in times])
    if (directory / 'metadata.json').is_file():
        try:
            cached = LampTimeline.load(directory)
            if np.array_equal(cached.times, stamps):
                return cached.metadata
        except (OSError, ValueError, KeyError):
            pass
    sensor = None
    weather_clock = None
    if trip.weather['mode'] != 'clear':
        from cloudlayers import sample_layers, sample_column

        @lru_cache(maxsize=2)
        def ambient_grid(stamp):
            when = datetime.fromtimestamp(stamp, timezone.utc)
            cover = sample_layers(grid_lon, grid_lat, when)
            tau = np.stack([sample_column(grid_lon, grid_lat, when, i)[0]
                            for i in range(3)], axis=-1)
            # Hemispheric diffuse illumination never uses the direct Sun-ray
            # shadow. A bounded two-stream-like closure reduces diffuse lux
            # with optical mass while retaining scattered daylight under cloud.
            attenuation = 1 / (1 + .35 * np.maximum(tau, 0))
            return np.clip(np.prod(1 - cover + cover * attenuation, axis=-1), .08, 1)

        grid_lon = grid_lat = None
        def sensor(lon, lat, when):
            nonlocal grid_lon, grid_lat
            if grid_lon is None:
                grid_lon, grid_lat = lon, lat
            stamp = utc_timestamp(when)
            before = float(np.floor(stamp / 900) * 900)
            fraction = (stamp - before) / 900
            return ambient_grid(before) * (1 - fraction) + ambient_grid(before + 900) * fraction

        if trip.weather['mode'] == 'illustrative_replay':
            extension = timedelta(minutes=WEATHER_HOLD_MINUTES)
            first = trip.legs[0].depart - (extension if trip.departure_hold_s else timedelta())
            last = trip.legs[-1].arrive + (extension if trip.arrival_hold_s else timedelta())
            sample_first = datetime.fromisoformat(trip.weather['sample_start'].replace('Z', '+00:00'))
            sample_last = datetime.fromisoformat(trip.weather['sample_end'].replace('Z', '+00:00'))
            def weather_clock(when):
                fraction = np.clip((when - first).total_seconds() / (last - first).total_seconds(), 0, 1)
                return sample_first + (sample_last - sample_first) * float(fraction)
    def solar(lon, lat, when):
        return unit_points(lon, lat) @ np.asarray(sun_direction(when))
    result = build_lamp_timeline(times, solar, sensor_transmission=sensor,
                                 weather_time=weather_clock, output_dir=directory)
    result.metadata['weather_policy'] = ('Clear sky.' if sensor is None else
        'Forecast-derived diffuse sensor estimate; pre-trip warmup clamps to available weather. '
        'Replay maps meteorology only; schedules and Sun use physical UTC. '
        'Frozen physical end holds preserve lamp state while rendered clouds may keep moving.')
    (directory / 'metadata.json').write_text(json.dumps(result.metadata, indent=2) + '\n')
    _timeline.cache_clear()
    return result.metadata


def city_emission(lon, lat, solar_cosine, solar_rate=-6., *, physical_dt=None, weather_dt=None):
    """Unclipped float32 linear source RGB before camera-ray attenuation.

    Lamp activation and occupancy belong to source radiance. Daylight contrast
    comes from additive scene radiance and the shared exposure/tone mapper.
    ``weather_dt`` is accepted for the renderer contract; weather influences
    sensors only through the immutable prepass, never mutable frame history.
    Without a physical timestamp, a clear-sky diagnostic approximation is used.
    """
    lon, lat, solar_cosine, solar_rate = np.broadcast_arrays(lon, lat, solar_cosine, solar_rate)
    shape = lon.shape
    texture = light_texture()
    height, width = texture.shape
    x = ((lon.ravel() / (2 * np.pi) + .5) * width - .5) % width
    y = np.clip((.5 - lat.ravel() / np.pi) * height - .5, 0, height - 1)
    level = map_coordinates(texture, np.array([y, x]), output=np.float32,
                            order=1, mode='grid-wrap', prefilter=False) / 255
    level = np.maximum(0, (level - .018) / .982) ** .82
    emission = np.zeros((len(level), 3), dtype=np.float32)
    lit = level > 0
    if not np.any(lit):
        return emission.reshape(shape + (3,))
    lo, la = lon.ravel()[lit], lat.ravel()[lit]
    fields = geographic_fields(lo, la)
    priors = regional_populations(lo, la, fields)
    colors = population_colors(lo, la, priors, fields)
    from lighting_profile import apply_population_profile
    colors, priors = apply_population_profile(_lighting_profile(), lo, la, physical_dt, colors, priors)
    if physical_dt is None:
        diagnostic = activation_components(solar_cosine.ravel()[lit], *fields,
                                             solar_rate.ravel()[lit])
        relay = np.stack((diagnostic['outdoor'], diagnostic['building']), axis=-1)
        schedules = np.ones((len(lo), 4), np.float32)
    else:
        relay = _timeline().sample(lo, la, physical_dt)
        schedules = schedule_fractions(lo, la, physical_dt, priors)
    active = np.stack((relay[:, 0], relay[:, 1], relay[:, 1], np.ones(len(lo))), axis=-1)
    # Different populations retain their own spectra as they switch or dim.
    # Each color has unit luminance, so the old scalar emission budget remains.
    contributions = priors['shares'] * schedules * active
    radiance = np.sum(contributions[..., None] * colors, axis=-2)
    from runtime import TRIP
    strength = float(TRIP.style.get('city_light_strength', 1.))
    emission[lit] = EMISSION_LUMINANCE * strength * level[lit, None] * radiance
    return emission.reshape(shape + (3,))
