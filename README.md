# Salad Chopping for Home Assistant

A custom integration that polls Salad every five minutes and adds USD sensors.

- **Current balance** shows the account balance available for redemption. It can decrease when you redeem rewards.
- **Lifetime earnings** shows the total Salad reports for each machine. New machines appear automatically when Salad lists them.
- **Earnings 24h, 7d, and 30d** show the total earned in each window and expose the hourly or daily earnings for dashboard charts.

## Install from Home Assistant Marketplace

1. In Home Assistant 2026.11 or later, go to **Settings → Marketplace → Add from link**.
2. Enter the [Salad Chopping repository URL](https://github.com/miyconst-ha/SaladChoppingStatsHa). Connect GitHub if prompted, then select **Add**.
3. Open **Salad Chopping** in Marketplace and select **Install**.
4. Follow the setup steps below. If you close the setup dialog, open **Settings → Devices & services → Add integration** and search for **Salad Chopping**.

A first install can open setup without a restart. If Home Assistant already loaded this integration, follow the restart prompt to apply the new code.

## Connect your Salad account

1. Sign in to the [Salad Earnings Summary](https://salad.com/earn/summary). Open your browser's developer tools, then go to **Application → Storage → Cookies → https://salad.com** in Chrome or Edge.
2. Copy the **Value** of the cookie named `auth`.
3. Paste the cookie value into the Salad Chopping setup dialog in Home Assistant.

Treat the cookie like a password. Home Assistant stores it in the integration's configuration, so protect access to the configuration directory and backups. If Salad expires the session, follow Home Assistant's reauthentication prompt and paste a fresh cookie from the same account.

## Add earnings graphs

1. After Salad Chopping's first successful history poll, open **Developer tools → Statistics** and search for **Salad earnings hourly** and **Salad earnings daily**. If you have multiple Salad accounts, choose the two IDs with the same account suffix.
2. In [salad-dashboard.yml](salad-dashboard.yml), replace the example statistic IDs with those IDs. The daily ID appears twice.
3. Paste the YAML into the **Raw configuration editor** of a new dashboard. To add it to an existing dashboard, copy the view entry into its `views` list.

The dashboard uses the built-in [Statistics Graph card](https://www.home-assistant.io/dashboards/statistics-graph/). The 24-hour chart uses one completed UTC hour per point. The 7-day and 30-day charts use one completed UTC day per point. The integration imports these buckets from Salad into Recorder, so the charts can show past earnings after the first successful poll.


## Publish a release

Push the contents of this folder to a public GitHub repository so `hacs.json`, this README, and `custom_components/` are at the repository root.

Publish a GitHub release tagged `v0.2.2` from the pushed commit. For later releases, update the version in `custom_components/salad_chopping/manifest.json` and use the matching GitHub release tag. Marketplace installs directly from the source tree.

## License

Copyright 2026 [miyconst-ha](https://github.com/miyconst-ha).

Salad Chopping is licensed under the [Apache License 2.0](LICENSE).
