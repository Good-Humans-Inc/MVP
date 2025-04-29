# monitor_notification_changes/main.py
import functions_framework
from firebase_admin import initialize_app, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import json
import requests
from datetime import datetime, timedelta, timezone
import base64

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
    # Print details about the event for debugging
    print(f"Received cloud event data type: {type(cloud_event.data)}")
    
    # Handle the event data
    try:
        # If data is bytes, try to decode it
        if isinstance(cloud_event.data, bytes):
            try:
                # Try to decode as JSON
                data_str = cloud_event.data.decode('utf-8')
                event_data = json.loads(data_str)
            except (UnicodeDecodeError, json.JSONDecodeError):
                # If that fails, print diagnostic info and return
                print(f"Unable to decode binary data. First few bytes: {cloud_event.data[:30]}")
                return
        elif isinstance(cloud_event.data, dict):
            # Data is already a dictionary
            event_data = cloud_event.data
        else:
            print(f"Unexpected data type: {type(cloud_event.data)}")
            return
    except Exception as e:
        print(f"Error processing event data: {str(e)}")
        return
    
    # Extract the document path from the event data
    # The structure might vary depending on how Eventarc formats the event
    resource_name = None
    user_id = None
    
    # Try various ways to find the document path and user ID
    try:
        if 'value' in event_data and 'name' in event_data['value']:
            resource_name = event_data['value']['name']
        elif 'document' in event_data:
            resource_name = event_data['document']
            
        # Log the resource name for debugging
        print(f"Resource name found: {resource_name}")
        
        if resource_name:
            # Extract user ID from the path
            parts = resource_name.split('/')
            if 'users' in parts:
                user_index = parts.index('users')
                if user_index + 1 < len(parts):
                    user_id = parts[user_index + 1]
        
        # If we still don't have a user ID, try to find it elsewhere
        if not user_id and 'value' in event_data and 'fields' in event_data['value']:
            if 'id' in event_data['value']['fields']:
                user_id = event_data['value']['fields']['id']['stringValue']
        
        if not user_id:
            print("Could not determine user ID from event")
            # Print more of the event data for debugging
            print(f"Event data: {json.dumps(event_data)[:500]}...")
            return
            
        print(f"Processing change for user: {user_id}")
    except Exception as e:
        print(f"Error extracting user ID: {str(e)}")
        return
    
    # Check if notification preferences were updated
    notification_updated = False
    try:
        if 'value' in event_data and 'updateMask' in event_data['value']:
            update_mask = event_data['value']['updateMask']
            if 'fieldPaths' in update_mask and 'notification_preferences' in update_mask['fieldPaths']:
                notification_updated = True
    except Exception as e:
        print(f"Error checking for notification preference updates: {str(e)}")
    
    # Even if we can't determine if notification preferences were updated,
    # we'll continue and handle the user's notification settings
    
    # Get the user document directly from Firestore
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            print(f"User document {user_id} no longer exists")
            return
        
        user_data = user_doc.to_dict()
    except Exception as e:
        print(f"Error retrieving user document: {str(e)}")
        return
    
    # Check if notifications are enabled
    notification_prefs = user_data.get('notification_preferences', {})
    is_enabled = notification_prefs.get('is_enabled', False)
    
    print(f"Notification preferences for user {user_id}: {notification_prefs}")
    print(f"Notifications enabled: {is_enabled}")
    
    if not is_enabled:
        print(f"Notifications are disabled for user {user_id}")
        # Cancel any scheduled notifications
        cancel_user_notifications(user_id)
        return
    
    # Get notification time
    hour = notification_prefs.get('hour')
    minute = notification_prefs.get('minute')
    
    if hour is None or minute is None:
        print(f"Invalid notification time for user {user_id}: hour={hour}, minute={minute}")
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
        response_data = schedule_notification(
            user_id=user_id,
            scheduled_time=next_time.isoformat(),
            is_one_time=False
        )
        
        # Update the user's next notification time
        user_ref.update({
            'next_notification_time': next_time
        })
        
        print(f"Successfully scheduled next notification for user {user_id} at {next_time.isoformat()}")
        if response_data:
            print(f"Schedule response: {response_data}")
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