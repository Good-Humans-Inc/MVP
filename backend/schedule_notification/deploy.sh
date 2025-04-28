#!/bin/bash

# Deploy schedule_notification function
gcloud functions deploy schedule_notification \
  --gen2 \
  --runtime=python310 \
  --region=us-central1 \
  --source=. \
  --entry-point=schedule_notification \
  --trigger-http \
  --memory=256Mi \
  --timeout=540s

# Deploy check_notifications function
gcloud functions deploy check_notifications \
  --gen2 \
  --runtime=python310 \
  --region=us-central1 \
  --source=. \
  --entry-point=check_notifications \
  --trigger-http \
  --memory=256Mi \
  --timeout=540s

# Deploy monitor_notification_changes function
gcloud functions deploy monitor_notification_changes \
  --gen2 \
  --runtime=python310 \
  --region=us-central1 \
  --source=. \
  --entry-point=monitor_notification_changes \
  --trigger-event-filters="type=google.cloud.firestore.document.v1.written" \
  --trigger-event-filters="database=pep-mvp" \
  --trigger-event-filters="namespace=(default)" \
  --trigger-event-filters="document=users/{userId}" \
  --trigger-location=nam5 \
  --memory=256Mi \
  --timeout=540s 