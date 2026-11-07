# Salad Chopping for Home Assistant

A custom integration that polls Salad every five minutes and adds USD sensors.

- **Current balance** shows the account balance available for redemption. It can decrease when you redeem rewards.
- **Lifetime earnings** shows the total Salad reports for each machine. New machines appear automatically when Salad lists them.
- **Earnings 24h, 7d, and 30d** show the total earned in each window and expose the hourly or daily earnings for dashboard charts.

## Install from Home Assistant Marketplace

1. In Home Assistant 2026.11 or later, go to **Settings → Marketplace → Add from link**.
2. Enter the public GitHub URL of this repository. Connect GitHub if prompted, then select **Add**.
3. Open **Salad Chopping** in Marketplace and select **Install**.
4. Follow the setup steps below. If you close the setup dialog, open **Settings → Devices & services → Add integration** and search for **Salad Chopping**.

A first install can open setup without a restart. If Home Assistant already loaded this integration, follow the restart prompt to apply the new code.

## Connect your Salad account

1. Sign in to the [Salad Earnings Summary](https://salad.com/earn/summary). Open your browser's developer tools, then go to **Application → Storage → Cookies → https://salad.com** in Chrome or Edge.
2. Copy the **Value** of the cookie named `auth`.
3. Paste the cookie value into the Salad Chopping setup dialog in Home Assistant.

Treat the cookie like a password. Home Assistant stores it in the integration's configuration, so protect access to the configuration directory and backups. If Salad expires the session, follow Home Assistant's reauthentication prompt and paste a fresh cookie from the same account.

## Add earnings graphs

Install [ApexCharts Card](https://github.com/RomRider/apexcharts-card), then paste the following into a manual card on your Home Assistant dashboard. Adjust the entity IDs if Home Assistant assigned different ones.

```yaml
type: vertical-stack
cards:
  - type: custom:apexcharts-card
    graph_span: 24h
    header:
      show: true
      title: Hourly earnings · Last 24 hours
    series:
      - entity: sensor.salad_earnings_24h
        type: column
        unit: USD
        float_precision: 4
        data_generator: |
          return entity.attributes.earnings ?? [];
  - type: custom:apexcharts-card
    graph_span: 7d
    header:
      show: true
      title: Daily earnings · Last 7 days
    series:
      - entity: sensor.salad_earnings_7d
        type: column
        unit: USD
        float_precision: 4
        data_generator: |
          return entity.attributes.earnings ?? [];
  - type: custom:apexcharts-card
    graph_span: 30d
    header:
      show: true
      title: Daily earnings · Last 30 days
    series:
      - entity: sensor.salad_earnings_30d
        type: column
        unit: USD
        float_precision: 4
        data_generator: |
          return entity.attributes.earnings ?? [];
```

The graphs use history from Salad's dashboard API and can display it as soon as the first poll succeeds. Each window sums earnings across the machines Salad currently lists for the account. Buckets use UTC boundaries and include the current partial hour or day. Empty buckets display zero after a successful history fetch. If the history request fails, the three window sensors become unavailable until a later poll succeeds.

## Publish a release

Push the contents of this folder to a public GitHub repository so `hacs.json`, this README, and `custom_components/` are at the repository root.

Publish a GitHub release tagged `v0.2.0` from the pushed commit. For later releases, update the version in `custom_components/salad_chopping/manifest.json` and use the matching GitHub release tag. Marketplace installs directly from the source tree.

## License

Copyright 2026 Salad Chopping contributors.

Salad Chopping is licensed under the [Apache License 2.0](LICENSE).
