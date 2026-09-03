---
name: android-daily-report-intake
description: "Deprecated compatibility wrapper for akbs-daily-report. Use only when an existing invocation still names android-daily-report-intake."
---

# Android Daily Report Intake Compatibility

Forward the unchanged arguments and exit status from
`scripts/android_daily_report_intake.py` to `akbs-daily-report`. Tell the user that
`$akbs-daily-report` is the replacement. This wrapper contains no report builder,
validator, or writer.
