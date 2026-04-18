# BMW CarData Home Assistant

This repository contains a Home Assistant custom integration for the official
BMW CarData API.

It uses BMW's documented Device Code Flow and the official read-only customer
API to expose vehicle data such as:

- current state of charge
- target state of charge
- remaining range
- odometer
- charging state and charging result
- charging connector status
- service interval warnings
- door, hood, and trunk state

It does not provide vehicle control. The official BMW CarData customer API
documented by BMW is a read-oriented data API, not a remote-control API.

## What This Integration Uses

- Official BMW CarData API:
  [API specification](https://bmw-cardata.bmwgroup.com/customer/public/api-specification)
- Official BMW CarData integration guide:
  [Integration guide](https://bmw-cardata.bmwgroup.com/customer/public/api-documentation)
- Official BMW telematics catalogue:
  [Telematics catalogue](https://www.bmw.de/de-de/mybmw/public/cardata-telematic-catalogue)

## Prerequisites

Before adding this integration to Home Assistant, make sure:

- you have a BMW account
- your vehicle is linked to that BMW account
- your BMW account is the `PRIMARY` user for the vehicle
- you can log in to the BMW CarData portal

## Step 1: Create A BMW CarData Client

Open the BMW CarData portal and create a CarData client:

- Go to the BMW CarData portal
- Create a new CarData client
- Copy the generated `Client ID`

You will use this `Client ID` later inside Home Assistant.

## Step 2: Subscribe The Client To CarData API

In the BMW CarData portal, subscribe the client to the CarData API service.

This step is important. BMW's own guide makes clear that subscription needs to
be done before device registration, otherwise the resulting tokens may not work
for the requested service.

For the first version of this integration, the required scope is:

- `cardata:api:read`

Streaming is intentionally not required for the first release.

## Step 3: Confirm Vehicle Mapping

Make sure your vehicle is mapped to the same BMW account you used for CarData.

The integration uses:

- `GET /customers/vehicles/mappings`

If BMW does not list your vehicle there, Home Assistant will not be able to set
up the integration successfully.

## Step 4: Install Through HACS

Install this repository as a custom integration through HACS.

General flow:

1. Open HACS in Home Assistant
2. Add this repository as a custom repository
3. Choose `Integration`
4. Install `BMW CarData`
5. Restart Home Assistant

## Step 5: Add The Integration In Home Assistant

After restart:

1. Open `Settings` -> `Devices & Services`
2. Click `Add Integration`
3. Search for `BMW CarData`
4. Enter your BMW CarData `Client ID`
5. Optionally enable location tracking

The integration will then start BMW's Device Code Flow.

## Step 6: Approve BMW Device Code Flow

Home Assistant will show:

- a BMW verification URL
- a short `user_code`

Open the BMW URL in your browser, enter the code, approve the device, and then
return to Home Assistant to continue setup.

After approval, the integration will:

1. exchange the device code for tokens
2. discover your mapped vehicles
3. let you choose one or more vehicles to include in Home Assistant
4. create or reuse a Home Assistant telematics container
5. perform the initial sync for each selected vehicle

## What The Integration Creates

The integration uses one curated telematics container and combines it with a
few dedicated BMW endpoints.

One BMW CarData config entry can expose multiple BMW vehicles from the same
BMW account. Each selected VIN appears in Home Assistant as a separate device
with its own entities.

Container-backed data:

- current SoC
- target SoC
- remaining range
- travelled distance
- charging status
- high-voltage charging status
- charge connector status
- selected service warning values
- door, hood, trunk, and charging-port state

Dedicated endpoint data:

- vehicle mappings
- `basicData`
- `chargingHistory`
- `locationBasedChargingSettings`

Some BMW data points only exist on dedicated endpoints and will not appear in
`telematicData` even if they are valid catalogue entries.

## Rate Limits And Freshness

BMW documents a limit of 50 API requests per day.

Because of that, this integration is intentionally conservative:

- main telematics data is polled hourly
- charging history is refreshed less often
- basic metadata is refreshed daily
- optional location-related charging settings are refreshed daily

Implications:

- data is not real-time
- some values only update after the vehicle reports new data to BMW
- some fields may stay `null` until the car is driving, charging, or otherwise
  generating new telemetry
- adding more vehicles to one account entry increases total API usage and may
  exhaust the shared daily budget sooner

## Known Limitations

- No remote control support
- No lock, unlock, climate start, honk, flash, or charge start/stop
- Location may remain unavailable even when the descriptors are valid
- Some charging-related fields are only meaningful while charging is active
- BMW-side delays can make timestamps look older than expected

## Privacy

This repository is intended to stay public. Example payloads and tests should
use sanitized fixture data only.

Do not commit:

- BMW `Client ID` values for real apps
- access tokens or refresh tokens
- real VINs
- location coordinates or location history
- other account-specific or vehicle-identifying data

## Troubleshooting

### Setup fails before authorization

Check:

- the `Client ID` is correct
- the CarData API subscription is enabled in the BMW portal
- the BMW portal account really owns the mapped vehicle

### Setup fails after authorization

Check:

- the vehicle appears in BMW CarData mappings
- you are the `PRIMARY` user
- BMW is not temporarily rate-limiting your account

### Data looks incomplete

That is often a BMW-side limitation rather than an integration bug.

Examples:

- location can be `null`
- some charging values are only available during or shortly after charging
- target SoC can update much less frequently than current SoC