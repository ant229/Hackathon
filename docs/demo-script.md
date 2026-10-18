# Park LU Demo Script (175 seconds)

All data is synthetic. Say so in the first ten seconds.

## Before You Present

1. Start the API: `cd api && uv sync` (once), then `uv run uvicorn app.main:create_app --factory --port 8000`. Wait until `http://localhost:8000/health` answers (about 1 s).
2. Start the web app: `cd web && npm install` (once), then `npm run dev`.
3. Open two browser windows side by side. Window A: `http://localhost:3000` (you drive it). Window B: `http://localhost:3000/map` (the watch window for step 4; leave it open).
4. In Window A open the Demo page and press **Reset**, so no old scenario is active.
5. Run the demo Monday to Saturday between 08:00 and 21:00 Eastern if you can. Outside those hours the street zones are not enforced, and Game Day skips them (fewer dials change).
6. Use light or dark mode, whichever projects better. The app follows the operating system setting.

## Timed Steps

| # | Time | Screen | Say and do |
|---|------|--------|------------|
| 1 | 0:00-0:20 (20 s) | Home (`/`) | "Park LU shows visitors to Lehigh where parking is open right now, and where it will be later. There are no sensors, so we estimate occupancy from pay-by-app sessions. All data here is synthetic, calibrated to published BPA and Lehigh rules." Point to the two live numbers (Open Spaces Now, Zones Opening Soon) and the Data Sources section. |
| 2 | 0:20-0:55 (35 s) | Map (`/map`) | Open Map. "Each pin is a zone: percent free, colored green at 40% or more, amber 15 to 39%, red under 15%. The label says it too, so color is never the only signal." Select one pin to open the panel: rate, time limit, spaces in use, note. Point out the opening-soon list ("spaces freeing up in the next 15 minutes"). |
| 3 | 0:55-1:30 (35 s) | Plan (`/plan`) | Pick **Zoellner Arts Center**, then the **Saturday 12 PM** chip. "We rank garages and meters by predicted availability (50%), price (20%) and walk time (30%)." Read the top result: rate, time limit, walk minutes, pay app, score components. Point out any "Busier than usual" event warning. |
| 4 | 1:30-2:15 (45 s) | Demo (`/demo`), then Window B (Map) | In Window A press **Game Day**. "A football game just started." Switch to Window B (do not reload it). Within 5 seconds the affected dials turn amber or red and the percentages drop. Switch back to Window A and point to the before and after table and the minutes-remaining countdown (45 min). |
| 5 | 2:15-2:55 (40 s) | Explore (`/explore`) | Open Explore. "This is an associative model of every session: pick anything and the rest re-filters." In the **Event** field select **Game Day (Live Demo)**. Show the Sessions, Average Stay, Revenue, Overstay Rate and Average Occupancy KPIs and the heatmap for just those sessions. Use Back in the Selection Bar, then Clear All. |

Total: 20 + 35 + 35 + 45 + 40 = 175 s (5 s of slack).

## After the Demo

Press **Reset** on the Demo page, or let the scenario expire after 45 minutes.

## If Something Goes Wrong

- Pins stay gray or the page says the API cannot be reached: confirm the API terminal is running, then select Try Again.
- "Live updates paused" on the map: the stream dropped. It reconnects within 3 s and reloads every zone.
- Few dials change on Game Day: you are outside enforcement hours (Mon-Sat 08:00-21:00). Say so, and show the Explore step instead.
- Plan shows 40+ minute walks: you picked Goodman Stadium. No visitor zone is near it. Use Zoellner Arts Center or 3rd Street shops.
