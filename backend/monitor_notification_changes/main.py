# monitor_notification_changes/main.py
import functions_framework
from firebase_admin import initialize_app, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import json
import requests
from datetime import datetime, timedelta, timezone

# Initialize Firebase app
try:
    app = initialize_app()
except ValueError:
    app = initialize_app()

db = firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.cloud_event
def monitor_notification_changes(cloud_event):
    """
    Firebase trigger function that monitors changes to user notification preferences.
    This function is triggered by Firestore document updates in the users collection.
    """
    # For Firestore triggers in Gen2, need to parse the data properly
    import json
    
    # First handle the data properly - it could be bytes or already parsed
    if isinstance(cloud_event.data, bytes):
        event_json = json.loads(cloud_event.data)
    else:
        event_json = cloud_event.data
        
    # Now get the value field
    if "value" not in event_json:
        print(f"Missing 'value' in event data: {event_json}")
        return
    
    event_data = event_json["value"]
    resource_name = event_data.get("name", "")
    
    # Extract the user ID from the resource name
    # Format: projects/{project_id}/databases/{database}/documents/users/{user_id}
    parts = resource_name.split('/')
    if len(parts) < 6 or parts[-2] != 'users':
        print(f"Invalid resource name: {resource_name}")
        return
    
    user_id = parts[-1]
    print(f"Processing change for user: {user_id}")
    
    # Check if this is an update event and notification_preferences field was updated
    if not event_data.get("updateMask") or "notification_preferences" not in event_data.get("updateMask", {}).get("fieldPaths", []):
        print(f"Not a notification preference update for user {user_id}")
        return
    
    # Get the updated user document
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        print(f"User document {user_id} no longer exists")
        return
    
    user_data = user_doc.to_dict()
    
    # Check if notifications are enabled
    notification_prefs = user_data.get('notification_preferences', {})
    is_enabled = notification_prefs.get('is_enabled', False)
    
    if not is_enabled:
        print(f"Notifications are disabled for user {user_id}")
        # Cancel any scheduled notifications
        cancel_user_notifications(user_id)
        return
    
    # Get notification time
    hour = notification_prefs.get('hour')
    minute = notification_prefs.get('minute')
    
    if hour is None or minute is None:
        print(f"Invalid notification time for user {user_id}")
        return
    
    # Calculate the next notification time
    now = datetime.now(timezone.utc)
    next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If the time has already passed today, schedule for tomorrow
    if next_time <= now:
        next_time = next_time + timedelta(days=1)
    
    # Cancel any existing scheduled notifications
    cancel_user_notifications(user_id)
    
    # Schedule the next notification
    try:
        schedule_notification(
            user_id=user_id,
            scheduled_time=next_time.isoformat(),
            is_one_time=False
        )
        
        # Update the user's next notification time
        user_ref.update({
            'next_notification_time': next_time
        })
        
        print(f"Successfully scheduled next notification for user {user_id} at {next_time.isoformat()}")
    except Exception as e:
        print(f"Error scheduling notification for user {user_id}: {str(e)}")

def cancel_user_notifications(user_id):
    """Cancel all scheduled notifications for a user."""
    # Get notifications with status 'scheduled'
    notifications = db.collection('notifications') \
        .where('user_id', '==', user_id) \
        .where('status', '==', 'scheduled') \
        .stream()
    
    cancelled_count = 0
    for notif in notifications:
        notif_data = notif.to_dict()
        task_name = notif_data.get('task_name')
        
        # Update notification status
        db.collection('notifications').document(notif.id).update({
            'status': 'cancelled',
            'updated_at': firestore.SERVER_TIMESTAMP,
            'cancelled_reason': 'User updated notification preferences'
        })
        
        # If we have task_name, try to delete the Cloud Task
        if task_name:
            try:
                from google.cloud import tasks_v2
                client = tasks_v2.CloudTasksClient()
                client.delete_task(name=task_name)
                print(f"Deleted Cloud Task: {task_name}")
            except Exception as e:
                print(f"Error deleting Cloud Task {task_name}: {str(e)}")
        
        cancelled_count += 1
    
    print(f"Cancelled {cancelled_count} notifications for user {user_id}")

def schedule_notification(user_id, scheduled_time, is_one_time=False, custom_title=None, custom_body=None):
    """Call the schedule_notification Cloud Function."""
    # Prepare the request payload
    payload = {
        'user_id': user_id,
        'scheduled_time': scheduled_time,
        'is_one_time': is_one_time
    }
    
    if custom_title:
        payload['custom_title'] = custom_title
    
    if custom_body:
        payload['custom_body'] = custom_body
    
    # URL of the schedule_notification Cloud Function
    url = f"https://us-central1-pepmvp.cloudfunctions.net/schedule_notification"
    
    # Make the HTTP request
    response = requests.post(url, json=payload)
    
    # Process the response
    if response.status_code == 200:
        return response.json()
    else:
        error_message = f"Failed to schedule notification: {response.text}"
        print(error_message)
        raise Exception(error_message)

# Helper function to serialize Firestore data for JSON
def serialize_firestore_data(data):
    """Helper function to serialize Firestore data for JSON."""
    if isinstance(data, dict):
        return {k: serialize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_firestore_data(item) for item in data]
    elif hasattr(data, 'datetime'):  # Handle Firestore Timestamp
        return data.datetime.isoformat()
    else:
        return data