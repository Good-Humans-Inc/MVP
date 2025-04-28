#!/bin/bash

# This script should be run in Google Cloud Shell where gcloud is available

# Deploy monitor_notification_changes function
echo "Deploying monitor_notification_changes function..."
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

echo "Deployment completed!" 