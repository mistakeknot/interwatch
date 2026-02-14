---
name: status
description: Show current drift health scores from the last scan without re-scanning
---

# Drift Status

Show the current drift health from the last scan.

Read `.interwatch/drift.json` from the project root:

```bash
cat .interwatch/drift.json 2>/dev/null || echo "No scan data found. Run /interwatch:watch first."
```

If scan data exists, display:
1. Summary table with confidence tiers per watchable
2. Last scan timestamp
3. Any watchables in Medium/High/Certain status with recommended actions

If no scan data exists, suggest running `/interwatch:watch`.
