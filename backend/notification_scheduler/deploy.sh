#!/bin/bash

echo "Deploying the check_due_notifications function..."
gcloud functions deploy check_due_notifications \
  --gen2 \
  --runtime=python310 \
  --region=us-central1 \
  --source=. \
  --entry-point=check_due_notifications \
  --trigger-http \
  --memory=256Mi \
  --timeout=540s \
  --allow-unauthenticated

# Get the function URL
FUNCTION_URL=$(gcloud functions describe check_due_notifications --gen2 --region=us-central1 --format='value(serviceConfig.uri)')

echo "Function URL: $FUNCTION_URL"

# Check if the scheduler job already exists
JOB_EXISTS=$(gcloud scheduler jobs describe notification-check-scheduler --location=us-central1 2>/dev/null || echo "NOT_FOUND")

# Create or update the scheduler job
if [[ "$JOB_EXISTS" == "NOT_FOUND" ]]; then
  echo "Creating new Cloud Scheduler job..."
  gcloud scheduler jobs create http notification-check-scheduler \
    --location=us-central1 \
    --schedule="*/5 * * * *" \
    --uri="$FUNCTION_URL" \
    --http-method=POST \
    --attempt-deadline=4m \
    --time-zone="UTC" \
    --headers="Content-Type=application/json" \
    --message-body="{}"
else
  echo "Updating existing Cloud Scheduler job..."
  gcloud scheduler jobs update http notification-check-scheduler \
    --location=us-central1 \
    --schedule="*/5 * * * *" \
    --uri="$FUNCTION_URL" \
    --http-method=POST \
    --attempt-deadline=4m \
    --time-zone="UTC" \
    --headers="Content-Type=application/json" \
    --message-body="{}"
fi

echo "Deployment completed!"
echo "Cloud Scheduler job 'notification-check-scheduler' will run every 5 minutes to check for due notifications." 