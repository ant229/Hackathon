---
inclusion: always
---
# Product: South Side Parking

Full project context, decisions, and history: `/project-context.xml`. Its `<current_state>` section is the source of truth.

## What we're building
A web app showing **where, when, and for how long** parking opens up around Lehigh University and South Bethlehem. 24-hour hackathon, software only, team of 3.

## Users
Students and **parents visiting Lehigh**. Assume they're on a phone, don't know the area, and don't know that the city (ParkMobile) and Lehigh (Passport) use different payment apps.

## Data signal
No sensors. Occupancy is estimated from **pay-by-hour payment sessions** (zone, start, paid-until) plus zone capacity. Real data isn't public, so `simulator/` generates realistic synthetic sessions calibrated to real rules and patterns (3rd St always full, Morton St quiet, campus busy on weekday class hours).

## Features (priority order)
1. Live map: zones colored by occupancy, "opening soon" (sessions expiring in 15 min).
2. Plan a visit: destination + arrival time -> ranked options with price, walk time, which app to pay with.
3. Insights: hour x day heatmap, dwell time and turnover.
4. Demo controls: game day / Family Weekend demand spikes.

## Demo story
"A parent is visiting for Saturday's game." Show the crunch, the recommendation, and spots opening soon.

## Non-goals
No accounts or auth. No license plates stored. No hardware. No new features after hour 18.
