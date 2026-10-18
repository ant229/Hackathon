# Requirements Document
## Introduction

SpotStack (working name; subtitle "South Bethlehem & Lehigh parking, live") is a web application that shows students and parents visiting Lehigh University where, when, and for how long parking is available around South Bethlehem and the Lehigh campus. No hardware sensors exist, so the system estimates availability from pay-by-hour payment sessions: each session carries a zone, a start time, and a paid-until time, and each zone carries rate and time-limit rules. Real session data is not publicly available, so the system runs entirely on synthetic data calibrated to published operator rules (rates, limits, enforcement hours) and known demand patterns.

This specification covers the full MVP in one spec across three lanes end-to-end: the data core (schema, seed data, simulator, event templates), the analytics API (live status, prediction, opening-soon, recommendation, associative exploration, demo scenarios), and the frontend experience (home page, live map, plan a visit, explore, demo control panel).

The build is local-first. The whole application runs on one laptop for the hackathon presentation: the API and the web app each start with one documented command, require no accounts, keys, or hosted services, and generate all data synthetically at startup. Cloud deployment is deferred to a later phase that reuses an existing deploy scaffold. The local build has no authentication, including on the demo scenario endpoint; access control is added before any deployment.

Two operators are modeled. The Bethlehem Parking Authority (BPA) runs the ParkBethlehem on-street meters (RapidPark and FlexPark zones) and South Side garages, and accepts the ParkMobile and PayByPhone apps plus pay stations. Lehigh Parking Services runs campus meters and visitor garage spaces paid through the Passport Parking app, with Text2Park at Farrington Square after 4 PM and on weekends. Occupancy is active sessions divided by zone capacity using raw sessions only, with no correction factor and no confidence band. Prediction is historical average occupancy per hour-of-week multiplied by an event boost, computed without any machine-learning library. The system stores no license plates and exposes aggregates only.

### Out of Scope for the Local Build

The following items are deferred to the deploy phase and carry no acceptance criteria in this spec:

- Supabase hosting of the schema, including PostGIS inside Postgres and SQL migrations applied with the Supabase CLI.
- Row-level security policies (formerly Requirement 2): public read-only access through the anonymous role, with writes restricted to the API service role.
- pg_cron scheduled refresh of materialized prediction views.
- Supabase Realtime on Zone_Status (the local build uses Server-Sent Events instead).
- Fly.io deployment of the API and simulator, Vercel deployment of the web app, and secret handling (service key in Fly secrets, anonymous key in the browser).
- Authentication and authorization of any kind.
- Real operator data feeds (Passport, ParkMobile, BPA); only the adapter seam and documentation are in scope.
- Machine-learning prediction models.
- Git commits, branches, pushes, and pull requests until the user approves.

## Glossary

- **Parking_Monitor**: The complete SpotStack application running locally, including the Web_App, Analytics_API, Simulator, Associative_Engine, and Data_Store.
- **Web_App**: The Next.js frontend that hosts the Home_Page, Live_Map, Plan_A_Visit, Explore_Page, and Demo_Control_Panel.
- **Analytics_API**: The FastAPI service that serves zone status, the Live_Stream, prediction, opening-soon, recommendation, exploration, and demo-scenario endpoints, and hosts the Simulator and Associative_Engine in the local build.
- **Data_Store**: The in-process store inside the Analytics_API that holds the nine-table schema for the local build; each table maps one-to-one to a table in the deferred Supabase database.
- **Simulator**: The background worker inside the Analytics_API process that generates synthetic Sessions and Events and updates Zone_Status.
- **Seed_Data**: The shared JSON fixture in the /fixtures directory that defines Operators, Facilities, Zones, Rate_Rules, Destinations, Event_Templates, demand curves, and Scenarios.
- **Session_Source**: The adapter interface through which the Analytics_API reads Session records.
- **Simulator_Source**: The Session_Source implementation backed by the Simulator; the only implementation in the local build.
- **Operator**: An organization that runs parking facilities. The two modeled Operators are BPA and Lehigh Parking Services.
- **Facility**: A garage, lot, or street location owned by one Operator, with a latitude and longitude.
- **Zone**: A priced subdivision of a Facility with a capacity, a visitor-access flag, a visitor-facing note, Rate_Rules, and one Zone_Status row.
- **Rate_Rule**: A pricing and time-limit rule attached to a Zone for one day of the week and one time window.
- **RapidPark_Zone**: A BPA on-street meter Zone priced at $2.50 per hour with a 120-minute time limit.
- **FlexPark_Zone**: A BPA on-street meter Zone priced at $1.50 per hour with a 180-minute time limit.
- **Enforcement_Hours**: The time window covered by a Zone's Rate_Rules; BPA on-street Enforcement_Hours are 08:00 to 21:00 Monday through Saturday.
- **Placeholder_Flag**: A boolean on a Seed_Data Rate_Rule that is true when the rate, time limit, or hours are not verified against a published operator source.
- **Session**: A single pay-by-hour parking payment with a Zone, Start_Time, Paid_Until, End_Time, and an optional Event tag.
- **Active_Session**: A Session whose Start_Time is at or before the evaluated time and whose End_Time is after the evaluated time.
- **Destination**: A named point of interest that a visitor parks near: Zoellner Arts Center, Goodman Stadium, Alumni Memorial Building, or 3rd Street shops.
- **Event**: A scheduled activity at a Destination with a start time, end time, and expected attendance that raises parking demand.
- **Event_Template**: A recurring Event definition in Seed_Data with a name, Destination, schedule rule, expected attendance, and per-Zone Demand_Boost multipliers.
- **Impacts**: The association between an Event and a Zone that carries a Demand_Boost multiplier of 1.0 or greater.
- **Boost_Window**: The interval from 2 hours before an Event's Start_Time to 1 hour after the Event's End_Time.
- **Event_Boost**: For a Zone at a time, the largest Demand_Boost among Impacts rows whose Event Boost_Window contains that time, or 1.0 when no such row exists.
- **Zone_Status**: The live, one-row-per-Zone table holding the occupancy ratio, Active_Session count, opening-soon count, and last-updated time.
- **Estimated_Occupancy**: The count of Active_Sessions in a Zone divided by the Zone's Capacity, using raw Sessions only.
- **Time_Limited_Zone**: A Zone whose applicable Rate_Rule at the evaluated time has a non-null Time_Limit_Min.
- **Opening_Soon**: For a Time_Limited_Zone, the count of Active_Sessions whose Paid_Until falls between the evaluated time and 15 minutes after the evaluated time, inclusive.
- **Hour_Of_Week**: An integer from 0 to 167 identifying one day-of-week and hour-of-day slot in America/New_York local time, where 0 is Monday 00:00 to 00:59.
- **Baseline_Occupancy**: The historical average Estimated_Occupancy for one Zone and one Hour_Of_Week, excluding samples inside any Boost_Window that Impacts that Zone.
- **Predicted_Occupancy**: The product of Baseline_Occupancy and Event_Boost, clamped to a maximum of 1.0.
- **Predicted_Availability**: 1.0 minus Predicted_Occupancy.
- **Straight_Line_Distance**: The great-circle distance in meters between two latitude and longitude points.
- **Walk_Minutes**: Straight_Line_Distance multiplied by a 1.3 detour factor, divided by 80 meters per minute, rounded up to the next whole minute.
- **Recommendation_Score**: The weighted sum of Predicted_Availability, Price_Score, and Walk_Score used to rank Plan_A_Visit results.
- **Price_Score**: A value from 0.0 to 1.0 equal to 1.0 minus the min-max normalized Hourly_Rate across the candidate Zones in one response, or 1.0 when all candidate rates are equal.
- **Walk_Score**: A value from 0.0 to 1.0 equal to 1.0 minus the min-max normalized Walk_Minutes across the candidate Zones in one response, or 1.0 when all candidate Walk_Minutes are equal.
- **Scenario**: A named demo demand spike: game_day, family_weekend, or reset.
- **Live_Stream**: The Server-Sent Events endpoint /stream that pushes Zone_Status changes from the Analytics_API to the Web_App.
- **Home_Page**: The Web_App landing view that explains SpotStack and shows live headline numbers.
- **Live_Map**: The Web_App map view that renders Zones as Availability_Dials.
- **Availability_Dial**: A map pin for one Zone that shows the percent of free spaces as text and as a dial fill.
- **Plan_A_Visit**: The Web_App view that ranks parking options for a chosen Destination and arrival time.
- **Explore_Page**: The Web_App view for associative exploration of Session history; replaces the former Insights page.
- **Demo_Control_Panel**: The Web_App view that triggers Scenarios during a presentation.
- **Associative_Engine**: The in-memory component of the Analytics_API that holds the associative data model of Session history and evaluates Selections.
- **Field**: One dimension of the associative data model, such as Zone or Day.
- **Field_Value**: One distinct value of a Field.
- **Symbol_Table**: The list of distinct Field_Values for one Field.
- **Row_Index**: For one Session row, the integer position of the row's value in each Field's Symbol_Table.
- **Selection**: The set of Field_Values a user has chosen in each Field; values within one Field combine with OR, and Fields combine with AND.
- **Associated_Rows**: The Session rows whose value in every Field with a Selection is one of that Field's selected Field_Values.
- **Field_Context**: For a Field F, the Session rows that satisfy the Selections in every Field except F.
- **Value_State**: One of five display states for a Field_Value: Selected, Possible, Alternative, Excluded, or Selected_Excluded.
- **Selection_Bar**: The Explore_Page control that lists current Selections and offers per-Field clear, Clear All, Back, and Forward.
- **Selection_History**: The ordered list of past Selections used by Back and Forward.
- **Time_Of_Week_Class**: A Field that classifies a Session's Start_Time as Weekday Class Hours, Weekday Evening, Weekend, or Overnight.
- **Stay_Length_Bucket**: A Field that classifies End_Time minus Start_Time as Under 30 Min, 30–59 Min, 1–2 H, 2–3 H, or 3 H or More.
- **Outcome**: A Field that classifies a Session as Left Early, On Time, or Overstayed by comparing End_Time with Paid_Until using a 5-minute tolerance.
- **Floating_Control**: A control layered above content: the bottom tab bar and the Live_Map overlay panel.
- **Compact_Width**: A viewport narrower than 768 CSS pixels.
- **Wide_Width**: A viewport 768 CSS pixels wide or wider.
- **Project_Documentation**: The README.md at the repository root and the files in the /docs directory.
- **Presenter_Script**: The timed demo script in /docs/demo-script.md.

## Requirements

### Requirement 1: Data Model and Schema

**User Story:** As a data core developer, I want one relational schema for operators, facilities, zones, rules, sessions, destinations, events, impacts, and live status, so that every lane builds against one shared contract that maps directly to the deferred Supabase database.

#### Acceptance Criteria

1. THE Data_Store SHALL model nine tables named Operator, Facility, Zone, Rate_Rule, Session, Destination, Event, Impacts, and Zone_Status.
2. THE Data_Store SHALL define Operator with columns Operator_ID as primary key, Name, and Pay_App, where Pay_App lists every payment app the Operator accepts.
3. THE Data_Store SHALL define Facility with columns Facility_ID as primary key, Operator_ID as a foreign key referencing Operator, Name, Type, Lat, and Lng, where Type is one of garage, lot, or street.
4. THE Data_Store SHALL define Zone with columns Zone_ID as primary key, Facility_ID as a foreign key referencing Facility, Name, Capacity as a positive integer, Visitor_Allowed as a boolean, and Note as optional visitor-facing text.
5. THE Data_Store SHALL define Rate_Rule with columns Rule_ID as primary key, Zone_ID as a foreign key referencing Zone, Day_Of_Week, Start_Time, End_Time, Hourly_Rate, and Time_Limit_Min, where a null Time_Limit_Min denotes no time limit.
6. THE Data_Store SHALL define Session with columns Session_ID as primary key, Zone_ID as a foreign key referencing Zone, Start_Time, Paid_Until, End_Time, and Event_ID as a nullable foreign key referencing Event.
7. THE Data_Store SHALL define Destination with columns Destination_ID as primary key, Name, Lat, and Lng.
8. THE Data_Store SHALL define Event with columns Event_ID as primary key, Destination_ID as a foreign key referencing Destination, Name, Start_Time, End_Time, and Expected_Attendance.
9. THE Data_Store SHALL define Impacts with a composite primary key of Event_ID and Zone_ID, foreign keys referencing Event and Zone respectively, and a Demand_Boost column.
10. THE Data_Store SHALL define Zone_Status with columns Zone_ID as primary key and foreign key referencing Zone, Occupied as a ratio from 0.0 to 1.0, Active_Sessions as a non-negative integer, Opening_Soon as a non-negative integer, and Updated_At.
11. THE Data_Store SHALL store Facility and Destination positions as WGS84 latitude and longitude in decimal degrees.
12. THE Data_Store SHALL enforce the relationships Operator to Facility as one-to-many, Facility to Zone as one-to-many, Zone to Rate_Rule as one-to-many, Zone to Session as one-to-many, Destination to Event as one-to-many, Event to Zone as many-to-many through Impacts, and Zone to Zone_Status as one-to-one.
13. THE Data_Store SHALL hold every timestamp as a timezone-aware value and evaluate day-of-week and hour-of-day in America/New_York local time.

### Requirement 2: Seed Data and Real-World Calibration

**User Story:** As a developer on any lane, I want seed data calibrated to published operator rules, so that all lanes develop against identical, realistic starting data and unverified values are clearly marked.

#### Acceptance Criteria

1. THE Seed_Data SHALL reside in the /fixtures directory as one JSON file that the Analytics_API reads at startup.
2. THE Seed_Data SHALL define the Operator BPA with a Pay_App value listing ParkMobile and PayByPhone, and the Operator Lehigh Parking Services with a Pay_App value of Passport Parking.
3. THE Seed_Data SHALL define each RapidPark_Zone with Rate_Rules of $2.50 per hour and a Time_Limit_Min of 120 for Monday through Saturday from 08:00 to 21:00.
4. THE Seed_Data SHALL define each FlexPark_Zone with Rate_Rules of $1.50 per hour and a Time_Limit_Min of 180 for Monday through Saturday from 08:00 to 21:00.
5. THE Seed_Data SHALL set the Note of each BPA on-street Zone to state that pay stations are accepted in addition to the ParkMobile and PayByPhone apps.
6. THE Seed_Data SHALL define BPA on-street Zones on Main Street, East 3rd Street, and Morton Avenue as calibration targets.
7. THE Seed_Data SHALL define the BPA garages Polk Street Garage with a total Capacity of 731 spaces and New Street Garage at 324 South New Street.
8. THE Seed_Data SHALL define Zoellner Garage Level 1 as a Lehigh Parking Services Zone with Visitor_Allowed set to true and Rate_Rules of $1.00 per hour ending at 23:00 on all seven days.
9. THE Seed_Data SHALL define Zoellner Garage Levels 2 through 4 as Lehigh Parking Services Zones with Visitor_Allowed set to false.
10. THE Seed_Data SHALL define the Farrington Square garage lower level as a Lehigh Parking Services Zone with a Capacity of 52, Visitor_Allowed set to true, and Rate_Rules of $1.00 per hour from 06:00 to 24:00 on all seven days.
11. THE Seed_Data SHALL set the Note of the Farrington Square Zone to state that Text2Park is available after 16:00 and on weekends.
12. THE Seed_Data SHALL define Lehigh Parking Services meter Zones on Packer Avenue and at Alumni garage Level 1 paid through Passport Parking.
13. THE Seed_Data SHALL set the Placeholder_Flag to true on each Rate_Rule whose rate, time limit, or hours are not verified against a published operator source.
14. THE Seed_Data SHALL record a source reference on each Rate_Rule whose Placeholder_Flag is false.
15. THE Seed_Data SHALL define Destinations for Zoellner Arts Center, Goodman Stadium, Alumni Memorial Building, and 3rd Street shops, each with a latitude and longitude.
16. THE Seed_Data SHALL define an hour-of-week target occupancy demand curve for each Zone.

### Requirement 3: Synthetic Session Simulator

**User Story:** As a data core developer, I want a simulator that generates synthetic sessions following real payment behavior, so that the application behaves realistically without access to private payment data.

#### Acceptance Criteria

1. WHEN the Analytics_API starts, THE Simulator SHALL generate at least 28 days of Session history ending at the current time.
2. THE Simulator SHALL generate each Session with a Start_Time inside the Enforcement_Hours of an applicable Rate_Rule for the Session's Zone.
3. THE Simulator SHALL generate each Session with a paid duration, Paid_Until minus Start_Time, that is a positive multiple of 15 minutes.
4. WHERE a Session's Zone is a Time_Limited_Zone at the Session's Start_Time, THE Simulator SHALL generate a paid duration no greater than the applicable Time_Limit_Min.
5. THE Simulator SHALL generate Session history in which the share of Sessions with the Outcome Left Early is between 15 percent and 40 percent.
6. THE Simulator SHALL generate Session history in which the share of Sessions with the Outcome Overstayed is between 5 percent and 20 percent.
7. THE Simulator SHALL generate arrivals so that, for each Zone and each Hour_Of_Week outside Boost_Windows, the mean Estimated_Occupancy across the Session history falls within 0.10 of the Zone's target occupancy from the Seed_Data demand curve.
8. THE Simulator SHALL keep the count of Active_Sessions in each Zone at or below the Zone's Capacity.
9. THE Simulator SHALL produce a mean Estimated_Occupancy of at least 0.85 for the Main Street and East 3rd Street Zones between 10:00 and 18:00 Monday through Saturday.
10. THE Simulator SHALL produce a turnover, measured as Sessions per space per day, for the Main Street and East 3rd Street Zones that is lower than the median turnover of all BPA on-street Zones.
11. THE Simulator SHALL produce a mean Estimated_Occupancy of at most 0.40 for the Morton Avenue Zones during Enforcement_Hours.
12. WHEN the Simulator generates a Session in a Zone whose Event_Boost at the Session's Start_Time is greater than 1.0, THE Simulator SHALL set the Session's Event_ID to the Event that supplies that Event_Boost.
13. WHILE the Analytics_API is running, THE Simulator SHALL advance the simulation to the current wall-clock time at intervals of 5 seconds or less.
14. WHERE a random seed is configured, THE Simulator SHALL produce identical Session history for identical random seed, Seed_Data, and start time.

### Requirement 4: Recurring Event Templates

**User Story:** As a presenter, I want events generated from recurring templates relative to the current date, so that the demo always shows upcoming games and performances and never goes stale.

#### Acceptance Criteria

1. WHEN the Analytics_API starts, THE Simulator SHALL generate Event records from every Event_Template across the interval from the start of Session history to 28 days after the current date.
2. THE Simulator SHALL generate Lehigh Football Home Game Events at Goodman Stadium from 12:00 to 16:00 on alternating Saturdays, with the first Saturday on or after the current date being a game day.
3. THE Simulator SHALL generate Zoellner Evening Performance Events at Zoellner Arts Center from 19:30 to 22:00 on every Friday and Saturday.
4. THE Simulator SHALL generate exactly one Family Weekend Event that starts on a Saturday within the 21 days after the current date and ends on the following Sunday.
5. THE Simulator SHALL compute every generated Event date relative to the date on which the Analytics_API starts.
6. WHEN the Simulator generates an Event from an Event_Template, THE Simulator SHALL create one Impacts row for each Zone listed in the Event_Template, carrying that Zone's Demand_Boost from the Event_Template.
7. THE Seed_Data SHALL define a Demand_Boost of 1.0 or greater for every Zone listed in an Event_Template.

### Requirement 5: Live Occupancy Status

**User Story:** As a visitor, I want each zone's live status to reflect current active sessions, so that the map and headline numbers show what is happening now.

#### Acceptance Criteria

1. WHILE the Analytics_API is running, THE Simulator SHALL set Active_Sessions in each Zone_Status row to the count of Active_Sessions in that Zone at the update time.
2. WHILE the Analytics_API is running, THE Simulator SHALL set Occupied in each Zone_Status row to the Zone's Estimated_Occupancy, using raw Sessions without any correction factor.
3. WHILE the Analytics_API is running, THE Simulator SHALL set Opening_Soon in each Zone_Status row for a Time_Limited_Zone to the Zone's Opening_Soon count at the update time.
4. WHILE the Analytics_API is running, THE Simulator SHALL set Opening_Soon to 0 in each Zone_Status row for a Zone that is not a Time_Limited_Zone at the update time.
5. WHEN the Simulator updates a Zone_Status row, THE Simulator SHALL set Updated_At to the time of the update.
6. WHILE the Analytics_API is running, THE Simulator SHALL update every Zone_Status row at intervals of 5 seconds or less.

### Requirement 6: Demand Prediction

**User Story:** As an analytics developer, I want availability prediction computed as historical average occupancy per hour-of-week times an event boost, so that predictions stay fast, explainable, and free of machine-learning dependencies.

#### Acceptance Criteria

1. WHEN the Simulator finishes generating Session history, THE Analytics_API SHALL compute Baseline_Occupancy for each Zone and each Hour_Of_Week from Estimated_Occupancy samples taken at least once per hour across the Session history.
2. THE Analytics_API SHALL exclude Estimated_Occupancy samples inside any Boost_Window that Impacts a Zone from that Zone's Baseline_Occupancy.
3. THE Analytics_API SHALL compute Event_Boost for a Zone at a time as the largest Demand_Boost among Impacts rows for that Zone whose Event Boost_Window contains that time, and as 1.0 when no such row exists.
4. THE Analytics_API SHALL compute Predicted_Occupancy as Baseline_Occupancy multiplied by Event_Boost, clamped to a maximum of 1.0.
5. THE Analytics_API SHALL compute Predicted_Availability as 1.0 minus Predicted_Occupancy.
6. THE Analytics_API SHALL compute predictions with arithmetic over the Data_Store, without any machine-learning library.
7. WHEN a client requests a prediction for a Zone and a time, THE Analytics_API SHALL return the Predicted_Availability, the Baseline_Occupancy, the Event_Boost, and the name of the Event supplying the Event_Boost, or null when Event_Boost is 1.0.

### Requirement 7: Live Map

**User Story:** As a visitor, I want a live map showing how many spaces are free in each zone, so that I can see at a glance where parking is likely open.

#### Acceptance Criteria

1. THE Live_Map SHALL render each Zone as an Availability_Dial at the Zone's Facility latitude and longitude.
2. THE Availability_Dial SHALL display the Zone's percent free, computed as (1.0 minus Occupied) multiplied by 100 and rounded to the nearest whole number, as text followed by "% free".
3. THE Availability_Dial SHALL fill the dial in proportion to percent free and color the dial green at 40 percent free or more, amber from 15 to 39 percent free, and red below 15 percent free.
4. WHEN the Live_Map loads, THE Live_Map SHALL read every Zone and Zone_Status value from the /zones endpoint.
5. WHEN the Live_Stream delivers a Zone_Status change, THE Live_Map SHALL update the affected Availability_Dial within 1 second of receipt without a page reload.
6. WHEN a user selects an Availability_Dial, THE Live_Map SHALL show the overlay panel with the Zone name, Facility name, Operator, Pay_App, current Hourly_Rate, Time_Limit_Min, Active_Sessions out of Capacity, Opening_Soon count, Note, and Updated_At.
7. THE Live_Map SHALL list the Zones returned by the /opening-soon endpoint for the current map center in the overlay panel.
8. IF the /opening-soon endpoint returns no Zones, THEN THE Live_Map SHALL show the message "No spaces opening in the next 15 minutes" with a link to Plan_A_Visit.
9. IF the Live_Stream connection drops, THEN THE Live_Map SHALL show the status text "Live updates paused" and attempt to reconnect at intervals of 5 seconds or less.
10. WHEN the Live_Stream reconnects, THE Live_Map SHALL reload every Zone_Status value from the /zones endpoint and remove the "Live updates paused" status text.
11. IF the map tiles fail to load, THEN THE Live_Map SHALL continue to render every Availability_Dial and the overlay panel over a plain background.
12. THE Live_Map SHALL make each Availability_Dial reachable by keyboard with an accessible name containing the Zone name and percent free.

### Requirement 8: Opening Soon

**User Story:** As a visitor, I want to see which time-limited zones nearby have sessions expiring in the next 15 minutes, so that I can head toward spaces about to open.

#### Acceptance Criteria

1. WHEN a client requests opening-soon data near a latitude and longitude, THE Analytics_API SHALL return, for each Time_Limited_Zone, the Opening_Soon count of Active_Sessions whose Paid_Until falls within the next 0 to 15 minutes inclusive.
2. THE Analytics_API SHALL omit from opening-soon results every Zone whose Opening_Soon count is 0.
3. THE Analytics_API SHALL rank opening-soon results by ascending Straight_Line_Distance from the requested latitude and longitude.
4. THE Analytics_API SHALL include in each opening-soon result the Zone_ID, Zone name, Facility name, Opening_Soon count, Straight_Line_Distance in meters, and Walk_Minutes.
5. THE Analytics_API SHALL return opening-soon results as aggregate counts per Zone without any individual Session or vehicle data.
6. IF the near parameter is not two comma-separated decimal numbers, THEN THE Analytics_API SHALL return HTTP 422 with an error code of invalid_parameter and a parameter value of near.

### Requirement 9: Plan a Visit

**User Story:** As a parent visiting Lehigh, I want to pick a destination and arrival time and get ranked parking options with price, walk time, and payment app, so that I can choose where to park before I leave.

#### Acceptance Criteria

1. WHEN the Plan_A_Visit view loads, THE Plan_A_Visit SHALL list the Destinations returned by the /destinations endpoint.
2. WHEN a visitor selects a Destination and an arrival time, THE Plan_A_Visit SHALL request the /recommend endpoint and display the returned Zones in ranked order.
3. THE Analytics_API SHALL limit /recommend candidate Zones to Zones with Visitor_Allowed set to true.
4. THE Analytics_API SHALL compute Walk_Minutes between the selected Destination and each candidate Zone's Facility as Straight_Line_Distance multiplied by 1.3, divided by 80 meters per minute, rounded up to the next whole minute.
5. THE Analytics_API SHALL exclude from /recommend results every candidate Zone with Walk_Minutes greater than 25.
6. IF fewer than 3 candidate Zones have Walk_Minutes of 25 or less, THEN THE Analytics_API SHALL add the remaining candidate Zones in ascending Walk_Minutes order until the results hold 3 Zones or no candidate Zones remain.
7. THE Analytics_API SHALL compute each result's Recommendation_Score as the availability weight multiplied by Predicted_Availability at the arrival time, plus the price weight multiplied by Price_Score, plus the walk weight multiplied by Walk_Score.
8. THE Analytics_API SHALL use default weights of 0.5 for availability, 0.2 for price, and 0.3 for walk, summing to 1.0.
9. THE Analytics_API SHALL order /recommend results by descending Recommendation_Score, breaking ties by ascending Walk_Minutes.
10. THE Analytics_API SHALL include the weights and, for each result, the Predicted_Availability, Price_Score, Walk_Score, and Recommendation_Score in the /recommend response.
11. THE Analytics_API SHALL include for each /recommend result the Hourly_Rate and Time_Limit_Min of the Rate_Rule applicable at the arrival time, the Operator's Pay_App, the Walk_Minutes, and the Zone's Note.
12. IF no Rate_Rule covers a candidate Zone at the arrival time, THEN THE Analytics_API SHALL report an Hourly_Rate of 0, a null Time_Limit_Min, and an enforced value of false for that Zone.
13. WHERE a candidate Zone has an Event_Boost greater than 1.0 at the arrival time, THE Analytics_API SHALL include an event warning naming the Event and the Event's Start_Time.
14. THE Plan_A_Visit SHALL display for each result the Hourly_Rate, Time_Limit_Min, Walk_Minutes, Pay_App, Note, event warning, and the score components as text.
15. IF the requested Destination does not exist, THEN THE Analytics_API SHALL return HTTP 404 with an error code of not_found and a message naming the requested Destination identifier.

### Requirement 10: Associative Data Model

**User Story:** As a visitor or judge exploring the data, I want session history loaded into an associative model inspired by the Qlik Associative Engine, so that any combination of fields can be explored instantly.

#### Acceptance Criteria

1. WHEN the Simulator finishes generating Session history, THE Associative_Engine SHALL load every Session from the Session_Source into the associative data model.
2. THE Associative_Engine SHALL hold one Symbol_Table per Field containing each distinct Field_Value once.
3. THE Associative_Engine SHALL hold one Row_Index per Session row, storing for each Field the integer position of the row's Field_Value in that Field's Symbol_Table.
4. THE Associative_Engine SHALL define at least the Fields Zone, Facility Type, Operator, Pay App, Visitor Access, Day, Arrival Hour, Time_Of_Week_Class, Event, Stay_Length_Bucket, Outcome, and Time Limit.
5. THE Associative_Engine SHALL derive the Day Field from the Session's Start_Time day-of-week and the Arrival Hour Field from the Session's Start_Time hour from 0 to 23.
6. THE Associative_Engine SHALL assign Time_Of_Week_Class as Weekday Class Hours for Monday through Friday 07:00 to 16:59, Weekday Evening for Monday through Friday 17:00 to 22:59, Weekend for Saturday and Sunday 07:00 to 22:59, and Overnight for every day 23:00 to 06:59.
7. THE Associative_Engine SHALL assign Stay_Length_Bucket from End_Time minus Start_Time as Under 30 Min, 30–59 Min, 1–2 H for 60 to 119 minutes, 2–3 H for 120 to 179 minutes, or 3 H or More.
8. THE Associative_Engine SHALL assign Outcome as Left Early when End_Time is more than 5 minutes before Paid_Until, Overstayed when End_Time is more than 5 minutes after Paid_Until, and On Time otherwise.
9. THE Associative_Engine SHALL assign the Event Field the name of the Session's tagged Event, or No Event when the Session has no Event_ID.
10. THE Associative_Engine SHALL assign the Time Limit Field from the Rate_Rule applicable at the Session's Start_Time, expressed in hours, or No Limit when Time_Limit_Min is null.
11. THE Associative_Engine SHALL assign the Visitor Access Field as Visitors Allowed or Permit Only from the Zone's Visitor_Allowed value.
12. WHEN the Simulator creates a Session after startup, THE Associative_Engine SHALL add the Session to the associative data model within 10 seconds of creation.

### Requirement 11: Associative Selections and Value States

**User Story:** As a user of the Explore page, I want selecting values in any field to filter every other field and show which values are related, so that I can discover patterns, including what my selections exclude.

#### Acceptance Criteria

1. WHEN a user selects one or more Field_Values, THE Associative_Engine SHALL compute Associated_Rows by combining selected Field_Values within one Field with OR and combining Fields with AND.
2. WHEN the Selection changes, THE Associative_Engine SHALL recompute the Value_State of every Field_Value in every Field.
3. THE Associative_Engine SHALL assign the Value_State Selected to a selected Field_Value that occurs in at least one row of the Field's Field_Context.
4. THE Associative_Engine SHALL assign the Value_State Selected_Excluded to a selected Field_Value that occurs in no row of the Field's Field_Context.
5. THE Associative_Engine SHALL assign the Value_State Possible to an unselected Field_Value that occurs in at least one of the Associated_Rows.
6. THE Associative_Engine SHALL assign the Value_State Alternative to an unselected Field_Value in a Field that has a Selection, where the Field_Value occurs in at least one row of the Field's Field_Context.
7. THE Associative_Engine SHALL assign the Value_State Excluded to an unselected Field_Value that occurs in no row of the Field's Field_Context.
8. THE Explore_Page SHALL display each Field_Value's Value_State with a text label or icon in addition to color.
9. WHEN a user clicks an unselected Field_Value whose Value_State is Possible or Alternative, THE Associative_Engine SHALL add the Field_Value to the Field's Selection.
10. WHEN a user clicks a Field_Value whose Value_State is Selected or Selected_Excluded, THE Associative_Engine SHALL remove the Field_Value from the Field's Selection.
11. WHEN a user clicks a Field_Value whose Value_State is Excluded, THE Associative_Engine SHALL set the Field's Selection to that Field_Value and clear the Selection in each other Field whose selected Field_Values share no Session row with the clicked Field_Value.
12. IF the Selection produced by clicking an Excluded Field_Value matches zero Session rows, THEN THE Associative_Engine SHALL clear the Selection in every Field other than the clicked Field.
13. THE Selection_Bar SHALL display each Field that has a Selection together with the Field's selected Field_Values.
14. WHEN a user activates the clear control for one Field in the Selection_Bar, THE Associative_Engine SHALL clear that Field's Selection and leave other Fields' Selections unchanged.
15. WHEN a user activates Clear All in the Selection_Bar, THE Associative_Engine SHALL clear the Selection in every Field.
16. WHEN a user activates Back in the Selection_Bar, THE Explore_Page SHALL restore the previous Selection from the Selection_History.
17. WHEN a user activates Forward in the Selection_Bar, THE Explore_Page SHALL restore the Selection that the most recent Back replaced.
18. WHEN a user changes the Selection after activating Back, THE Explore_Page SHALL discard the Selection_History entries available to Forward.
19. WHILE no earlier Selection exists in the Selection_History, THE Selection_Bar SHALL show Back as disabled.
20. WHILE no later Selection exists in the Selection_History, THE Selection_Bar SHALL show Forward as disabled.
21. WHEN the Selection changes, THE Associative_Engine SHALL return Value_States, KPIs, and chart data within 300 milliseconds for a model of up to 100,000 Session rows.

### Requirement 12: Explore Page KPIs and Charts

**User Story:** As a visitor planning ahead, I want KPIs and charts that recompute on every selection, so that I can understand when and where parking is hard to find and how long people stay.

#### Acceptance Criteria

1. THE Explore_Page SHALL present a list of Field_Values for every Field, the Selection_Bar, the KPIs, and the charts on one view.
2. THE Explore_Page SHALL present a Sessions KPI equal to the count of Associated_Rows.
3. THE Explore_Page SHALL present an Average Stay KPI equal to the mean of End_Time minus Start_Time in minutes across Associated_Rows.
4. THE Explore_Page SHALL present a Revenue KPI equal to the sum across Associated_Rows of the applicable Hourly_Rate multiplied by Paid_Until minus Start_Time in hours.
5. THE Explore_Page SHALL present an Overstay Rate KPI equal to the share of Associated_Rows whose Outcome is Overstayed.
6. THE Explore_Page SHALL present an Average Occupancy KPI equal to the occupied space-hours of Associated_Rows divided by the available space-hours of the associated Zones across the days and hours in the Selection.
7. THE Explore_Page SHALL present an occupancy heatmap of 7 day rows by 24 hour columns, where each cell shows the Average Occupancy for the Associated_Rows in that Day and Arrival Hour.
8. THE Explore_Page SHALL present a Sessions by Zone bar chart, a stay-length distribution chart by Stay_Length_Bucket, and a turnover chart showing Sessions per space per day for each associated Zone.
9. WHEN the Selection changes, THE Explore_Page SHALL replace every KPI value, the heatmap, and every chart with values computed from the new Associated_Rows.
10. WHEN a user selects a heatmap cell, THE Associative_Engine SHALL set the Day Selection to the cell's day and the Arrival Hour Selection to the cell's hour.
11. WHEN a user selects a bar in the Sessions by Zone chart or the turnover chart, THE Associative_Engine SHALL add the bar's Zone to the Zone Selection.
12. WHEN a user selects a bar in the stay-length distribution chart, THE Associative_Engine SHALL add the bar's Stay_Length_Bucket to the Stay_Length_Bucket Selection.
13. THE Explore_Page SHALL give each heatmap cell and chart bar an accessible name containing the cell or bar label and value as text.
14. IF the Selection matches zero Session rows, THEN THE Explore_Page SHALL show the message "No sessions match these selections" with a Clear All control.

### Requirement 13: Demo Control Panel and Scenarios

**User Story:** As a presenter, I want a control panel that spikes simulated demand for game day and Family Weekend, so that I can show the map, numbers, and explore view responding live.

#### Acceptance Criteria

1. THE Demo_Control_Panel SHALL present controls labeled Game Day, Family Weekend, and Reset that send the Scenarios game_day, family_weekend, and reset to the /demo/scenario endpoint.
2. WHEN the Analytics_API receives the game_day or family_weekend Scenario, THE Simulator SHALL create an Event starting at the trigger time from the matching Event_Template, with Impacts rows copied from that Event_Template.
3. WHEN the Simulator applies a game_day or family_weekend Scenario, THE Simulator SHALL inject Sessions before the /demo/scenario response returns so that each affected Zone's Occupied equals the lesser of 0.95 and the greater of the Zone's Occupied before the trigger plus 0.25 and the Zone's Predicted_Occupancy with the Scenario's Event_Boost.
4. IF an affected Zone's Occupied before the trigger is 0.95 or greater, THEN THE Simulator SHALL leave that Zone's Occupied unchanged.
5. THE Simulator SHALL set the Event_ID of every injected Session to the Scenario's Event and generate injected Sessions that follow the 15-minute payment increments and Time_Limit_Min rules of Requirement 3.
6. THE Analytics_API SHALL return in the /demo/scenario response the Zone_ID, Zone name, Occupied before the trigger, and Occupied after the trigger for each affected Zone.
7. THE Demo_Control_Panel SHALL display the before and after occupancy of each affected Zone as percentages in text, the active Scenario name, and the minutes remaining until the Scenario expires.
8. WHEN a Scenario changes Zone_Status values, THE Live_Stream SHALL deliver the changed Zone_Status rows to connected clients within 5 seconds.
9. WHEN 45 minutes elapse after a Scenario is triggered, THE Simulator SHALL deactivate the Scenario and resume generating arrivals from the Zone demand curves without the Scenario's Event_Boost.
10. WHEN the Analytics_API receives the reset Scenario, THE Simulator SHALL end every injected Session at the reset time and deactivate the active Scenario.
11. WHEN the Analytics_API receives a game_day or family_weekend Scenario while another Scenario is active, THE Simulator SHALL end the active Scenario's injected Sessions and apply the new Scenario.
12. IF the /demo/scenario request names a Scenario other than game_day, family_weekend, or reset, THEN THE Analytics_API SHALL return HTTP 400 with an error code of unknown_scenario and the list of allowed Scenario names.

### Requirement 14: Home Page

**User Story:** As a judge or first-time visitor, I want a home page that explains SpotStack in one sentence and shows live numbers, so that I understand the product and its value within seconds.

#### Acceptance Criteria

1. THE Home_Page SHALL display the name SpotStack with the subtitle "South Bethlehem & Lehigh parking, live".
2. THE Home_Page SHALL display a one-sentence description of what SpotStack does.
3. THE Home_Page SHALL display the number of open spaces now, computed as the sum of Capacity minus Active_Sessions across Zones with Visitor_Allowed set to true.
4. THE Home_Page SHALL display the number of Zones opening soon, computed as the count of Zones whose Zone_Status Opening_Soon is greater than 0.
5. WHEN the Live_Stream delivers a Zone_Status change, THE Home_Page SHALL update both headline numbers without a page reload.
6. THE Home_Page SHALL link to the Live_Map, Plan_A_Visit, and Explore_Page.
7. THE Home_Page SHALL present a Data Sources section stating that all data is synthetic, calibrated to published BPA and Lehigh Parking Services rules, with unverified values flagged as placeholders.
8. THE Home_Page SHALL present in the Data Sources section the integration roadmap naming the Passport partner API, the ParkMobile partner portal, and the BPA garage availability map.

### Requirement 15: Analytics API Endpoints

**User Story:** As a frontend developer, I want a stable set of API endpoints with consistent errors, so that I can build the experience against a known contract.

#### Acceptance Criteria

1. THE Analytics_API SHALL expose GET /zones returning every Zone with the Zone's Facility name, Facility Type, Operator, Pay_App, Note, Lat, Lng, Capacity, Visitor_Allowed, Zone_Status values, and the Hourly_Rate, Time_Limit_Min, and enforced flag of the Rate_Rule applicable now.
2. THE Analytics_API SHALL expose GET /stream as a Server-Sent Events stream with content type text/event-stream.
3. WHEN a client connects to /stream, THE Analytics_API SHALL send one event containing every Zone_Status row.
4. WHEN the Simulator updates Zone_Status, THE Analytics_API SHALL send the changed Zone_Status rows to every connected /stream client within 5 seconds.
5. WHILE a /stream client is connected, THE Analytics_API SHALL send a heartbeat at intervals of 15 seconds or less.
6. THE Analytics_API SHALL expose GET /destinations returning every Destination with Destination_ID, Name, Lat, and Lng.
7. THE Analytics_API SHALL expose GET /predict accepting the parameters zone and time and returning the values defined in Requirement 6.
8. THE Analytics_API SHALL expose GET /opening-soon accepting the parameter near as latitude and longitude and returning the values defined in Requirement 8.
9. THE Analytics_API SHALL expose GET /recommend accepting the parameters destination and arrival, plus an optional limit from 1 to 20 with a default of 5, and returning the values defined in Requirement 9.
10. THE Analytics_API SHALL expose POST /demo/scenario accepting a JSON body with a scenario value and returning the values defined in Requirement 13.
11. THE Analytics_API SHALL expose GET /explore/model returning every Field, every Field's Symbol_Table values, and the total Session row count.
12. THE Analytics_API SHALL expose POST /explore/query accepting a Selection and returning every Field_Value's Value_State, the KPIs, the heatmap, and the chart data.
13. THE Analytics_API SHALL expose POST /explore/select accepting a Selection plus one clicked Field and Field_Value, and returning the resulting Selection together with every Field_Value's Value_State, the KPIs, the heatmap, and the chart data.
14. IF a request omits a required parameter, THEN THE Analytics_API SHALL return HTTP 422 with a JSON body containing an error code of missing_parameter, a parameter value naming the missing parameter, and a message.
15. IF a request supplies a parameter value that fails validation, THEN THE Analytics_API SHALL return HTTP 422 with a JSON body containing an error code of invalid_parameter, a parameter value naming the parameter, and a message.
16. IF a request references a Zone or Destination identifier that does not exist, THEN THE Analytics_API SHALL return HTTP 404 with an error code of not_found and a message naming the identifier.
17. IF an /explore/query or /explore/select request names a Field or Field_Value absent from the associative data model, THEN THE Analytics_API SHALL return HTTP 422 with an error code of invalid_parameter naming the unknown Field or Field_Value.
18. THE Analytics_API SHALL accept cross-origin requests from the Web_App origin http://localhost:3000.

### Requirement 16: Privacy

**User Story:** As a visitor, I want assurance that the system holds no license plate data and exposes only aggregates, so that my parking activity is not personally tracked.

#### Acceptance Criteria

1. THE Data_Store SHALL define no license plate column in any table.
2. THE Analytics_API SHALL return only aggregate parking data and exclude every individual vehicle or person identifier from every response.
3. THE Associative_Engine SHALL return only counts, sums, averages, Field_Values, and Value_States, and exclude Session_ID values and row-level Session records from every response.
4. THE Explore_Page SHALL present only aggregate occupancy, stay, revenue, overstay, and turnover data.

### Requirement 17: UI Design and Accessibility

**User Story:** As a visitor on a phone or laptop, I want a clear, accessible interface grounded in Apple's design foundations, so that I can read and use SpotStack comfortably in light or dark appearance, with assistive technologies, and with reduced motion.

#### Acceptance Criteria

1. THE Web_App SHALL render all text in the system font stack beginning with -apple-system, BlinkMacSystemFont, and system-ui.
2. THE Web_App SHALL render body text at 17 CSS pixels.
3. THE Web_App SHALL render every text element at 12 CSS pixels or larger.
4. THE Web_App SHALL give every interactive target a hit area of at least 44 by 44 CSS pixels.
5. THE Web_App SHALL render text with a contrast ratio of at least 4.5:1 against the text's background, or at least 3:1 for text that is 18 CSS pixels or larger or bold.
6. THE Web_App SHALL provide light and dark appearances and select between them solely from the operating system prefers-color-scheme setting.
7. THE Web_App SHALL pair every color-coded meaning with a text label, icon, or pattern that conveys the same meaning.
8. WHILE the operating system reports prefers-reduced-motion as reduce, THE Web_App SHALL replace map fly-to animations, dial transitions, and chart transitions with instant changes.
9. WHILE the operating system reports prefers-reduced-transparency as reduce, THE Web_App SHALL render every Floating_Control with an opaque background.
10. THE Web_App SHALL apply translucent or blurred material only to Floating_Controls and render every content surface with an opaque background.
11. WHILE the viewport is at Compact_Width, THE Web_App SHALL present navigation as a bottom tab bar with the tabs Home, Map, Plan, Explore, and Demo.
12. WHILE the viewport is at Wide_Width, THE Web_App SHALL present the same navigation destinations as a sidebar.
13. WHEN an interactive element receives keyboard focus, THE Web_App SHALL show a visible focus indicator with a contrast ratio of at least 3:1 against adjacent colors.
14. THE Web_App SHALL use title-style capitalization for every button label, tab label, and view title.
15. IF a request from the Web_App to the Analytics_API fails, THEN THE Web_App SHALL show an error message that states what went wrong and how to fix the problem, with a Try Again control.
16. IF the Analytics_API is unreachable, THEN THE Web_App SHALL show a message stating that the SpotStack API cannot be reached and naming the documented command that starts the Analytics_API.
17. WHEN a view has no data to show, THE Web_App SHALL show an empty state that describes the situation and offers a control for the next action.

### Requirement 18: Integration Readiness

**User Story:** As a team planning a real deployment, I want session data to flow through an adapter interface with documented real-world adapters, so that real operator data can replace the simulator without changing the API, engine, or UI.

#### Acceptance Criteria

1. THE Analytics_API SHALL read every Session through the Session_Source interface.
2. THE Parking_Monitor SHALL provide the Simulator_Source as the only Session_Source implementation in the local build.
3. THE Session_Source SHALL define the Session record with only the fields Zone_ID, Start_Time, Paid_Until, End_Time, and Event_ID.
4. THE Session_Source SHALL require every adapter to drop license plates and personal identifiers before Session records reach the Data_Store.
5. THE Project_Documentation SHALL describe a planned Passport adapter for Lehigh Parking Services that uses the Passport partner REST API with OAuth client credentials issued to approved partners, mapping the parking environment export to Zone and Rate_Rule and session events to Session.
6. THE Project_Documentation SHALL describe a planned ParkMobile adapter for BPA Sessions that requires sign-up through the gated ParkMobile partner developer portal.
7. THE Project_Documentation SHALL describe the BPA public garage availability map as a calibration and ground-truth source for BPA garage Zones.
8. THE Project_Documentation SHALL state that real integration requires data agreements with BPA and Lehigh Parking Services.

### Requirement 19: Hackathon Deliverables

**User Story:** As the team presenting to judges, I want Devpost-ready documentation and a scripted demo, so that the submission scores well on technical implementation, design, impact, idea quality, and demo.

#### Acceptance Criteria

1. THE Project_Documentation SHALL include a README.md with the sections Inspiration, What It Does, How We Built It, Challenges We Ran Into, Accomplishments That We're Proud Of, What We Learned, and What's Next.
2. THE Project_Documentation SHALL include in README.md run instructions listing prerequisites, the single command that starts the Analytics_API, the single command that starts the Web_App, and the local URLs of both.
3. THE Project_Documentation SHALL document in README.md the Estimated_Occupancy, Predicted_Occupancy, Walk_Minutes, and Recommendation_Score formulas with the default weights, and state that all data is synthetic.
4. THE Project_Documentation SHALL include the Presenter_Script with timed steps whose durations total 180 seconds or less, covering the Home_Page, Live_Map, Plan_A_Visit, Demo_Control_Panel, and Explore_Page.
5. THE Presenter_Script SHALL script the demo moment in which the presenter triggers Game Day, the Live_Map recolors affected Availability_Dials within 5 seconds without a page reload, and the presenter selects the Game Day Event in the Explore_Page to show the Event's Sessions and KPIs.
6. WHEN the presenter triggers a Scenario, THE Explore_Page SHALL list the Scenario's Event as a Field_Value of the Event Field within 10 seconds.

### Requirement 20: Local Run Baseline

**User Story:** As a team presenting from one laptop, I want the whole app to run locally with fake data and no cloud accounts, so that the demo works anywhere and every milestone has a working build.

#### Acceptance Criteria

1. THE Parking_Monitor SHALL start the Analytics_API, including the Simulator and Associative_Engine, with one documented command run from the /api directory.
2. THE Parking_Monitor SHALL start the Web_App with one documented command run from the /web directory.
3. THE Parking_Monitor SHALL run without user accounts, API keys, or hosted cloud services, apart from public map tile requests.
4. WHEN the Analytics_API starts, THE Parking_Monitor SHALL generate all Session, Event, Impacts, and Zone_Status data synthetically from the Seed_Data.
5. WHEN the Analytics_API start command runs, THE Analytics_API SHALL accept requests within 30 seconds.
6. THE Web_App SHALL read the Analytics_API base URL from the NEXT_PUBLIC_API_URL environment variable, with a default of http://localhost:8000.
7. THE Parking_Monitor SHALL list every environment variable name, without values, in the .env.example file.
8. THE Parking_Monitor SHALL provide automated Analytics_API tests runnable with one documented command and Web_App type checking and linting runnable with one documented command.
