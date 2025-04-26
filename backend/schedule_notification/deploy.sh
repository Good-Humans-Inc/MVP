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