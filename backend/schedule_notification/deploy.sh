#!/bin/bash

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
  --trigger-location=nam5 