---
name: android-weekly-report-intake
description: "Deprecated compatibility wrapper for akbs-weekly-report. Use only when an existing invocation still names android-weekly-report-intake."
---

# Android Weekly Report Intake Compatibility

Forward the unchanged arguments and exit status from
`scripts/android_weekly_report_intake.py` to `akbs-weekly-report`. Tell the user that
`$akbs-weekly-report` is the replacement. This wrapper contains no report builder,
validator, or writer.
