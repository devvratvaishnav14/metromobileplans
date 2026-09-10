# manual_example — schema demo, NOT a real carrier

These files exercise the `official_manual` / `trusted_secondary` import path in
tests. `example-mobile` is not a real provider and this data must never be loaded
into the real database. It only demonstrates the manifest shape an operator fills
in when importing a carrier that blocks automated retrieval:

    metromobile import \
      --manifest fixtures/manual_example/manifest.json \
      --capture  fixtures/manual_example/capture.html \
      --operator <your-name> \
      --verified-at 2026-09-03T14:00:00Z
