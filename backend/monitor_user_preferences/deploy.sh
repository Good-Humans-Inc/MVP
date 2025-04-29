#!/bin/bash

# Set project ID
PROJECT_ID="pepmvp"
REGION="us-central1"
FUNCTION_NAME="monitor-user-preferences"

# Deploy the Cloud Function
gcloud functions deploy $FUNCTION_NAME \
  --gen2 \
  --runtime=python310 \
  --region=$REGION \
  --source=. \
  --entry-point=monitor_user_preferences \
  --trigger-event-filters="type=google.cloud.firestore.document.v1.updated" \
  --trigger-event-filters="database=(default)" \
  --trigger-event-filters="namespace=(default)" \
  --trigger-event-filters="document=users/{userId}" \
  --trigger-event-filters-path-pattern="document.name" \
  --service-account="$PROJECT_ID@appspot.gserviceaccount.com"

echo "Deployment complete for $FUNCTION_NAME" 