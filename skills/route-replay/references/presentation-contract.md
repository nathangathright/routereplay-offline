# Continuous stops and restrained HUD

## Animate a layover, do not freeze a still

A positive `video.layover_hold_s` or entry in `video.layover_holds_s` interpolates the entire physical connection with a smooth monotonic clock. During that stop, the camera and aircraft airport position remain fixed while Sun, Moon, stars, city-light state and dated weather continue to change. Physical and weather UTC advance together for matching forecast/historical weather. Explicit replay maps the weather clock separately; it does not freeze it. A zero-second hold is an intentional cut, not an animated stop.

Give a long connection enough presentation time to read. Check multiple consecutive frames from the beginning, middle and end of the stop, not only its endpoints. Verify distinct physical/weather timestamps, changing solar direction and weather sampling. A changing clock alone does not demonstrate moving clouds when `weather.mode` is `clear`.

When weather is part of the requested film, try the explicit matching-date acquisition workflow before omitting it. Do not choose clear skies merely to shorten a render. Report unavailable source data or a coverage gap rather than substituting other dates without labeling replay. GFS imagery is reconstructed forecast weather, not individual-cloud observations.

## Airport labels and other text

The default film contains only split-flap airport codes. The trip title and provisional-data explanations belong in metadata, the delivery message and source notes. Do not add persistent title, disclaimer or status banners to the film unless requested. Telemetry and local media remain opt-in.

Only the endpoints of the current flight are introduced. A destination label first appears when its airport becomes visible during the incoming flight. It uses a fixed screen slot throughout the approach. At arrival its anchor locks to the ground; the panel stays in place during the stop because the camera is stationary, then recedes with the ground after departure. A departed visit retires before the following leg begins, even if a short or polar route keeps its anchor visible. Repeated visits have separate lifetimes.

Slots are chosen before rendering from geographic order and visibility. They must not chase the airport marker or depend on frame evaluation order. Inspect leader lines, proximity, airport-marker clearance, the centered aircraft exclusion area and simultaneous panels. A numeric pass does not excuse unreadable or misplaced lettering. Check the final decoded output at phone size and at each handoff.

Telemetry, when requested, occupies its compact top readout. Optional media cards fit below the centered aircraft and telemetry, but may collide with geographic airport labels, so they need their own visual check. No automatic captions are added.
