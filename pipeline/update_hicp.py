name: Update HICP data

on:
  schedule:
    # Eurostat publishes the flash estimate at the end of the month and the full
    # release around the middle, so twice a month covers both.
    - cron: "0 6 5,20 * *"
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - "pipeline/**"
      - ".github/workflows/update-hicp.yml"

jobs:
  update:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Fetch Eurostat HICP
        run: python pipeline/update_hicp.py

      - name: Commit if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/hicp-anual.json
          git diff --staged --quiet || git commit -m "Update HICP data"
          git push
