#!/bin/bash

# Deploy the Cloud Function first
gcloud functions deploy schedule_daily_notifications \
  --gen2 \
  --runtime=python310 \
  --region=us-central1 \
  --source=. \
  --entry-point=schedule_daily_notifications \
  --trigger-http \
  --memory=256Mi \
  --timeout=540s

# Get the function URL
FUNCTION_URL=$(gcloud functions describe schedule_daily_notifications --gen2 --region=us-central1 --format='value(serviceConfig.uri)')

# Create a Cloud Scheduler job to run daily at 00:01 UTC
gcloud scheduler jobs create http daily-notification-scheduler \
  --schedule="1 0 * * *" \
  --uri="$FUNCTION_URL" \
  --http-method=POST \
  --attempt-deadline=540s \
  --time-zone="UTC" \
  --location=us-central1 \
  --headers="Content-Type=application/json" \
  --message-body="{}" 