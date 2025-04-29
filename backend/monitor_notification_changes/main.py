# monitor_notification_changes/main.py
import functions_framework
# Firebase Admin imports for database operations
import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore
from firebase_admin import messaging

import json
import requests
from datetime import datetime, timedelta, timezone
import uuid
import sys

# Initialize Firebase Admin
try:
    app = firebase_admin.initialize_app()
except ValueError:
    app = firebase_admin.get_app()

# Create Firestore client - using the admin_firestore module
db = admin_firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.cloud_event
def monitor_notification_changes(cloud_event):
    """Triggered by a change to a Firestore document."""
    print("🔔 FUNCTION TRIGGERED - STARTING EXECUTION", file=sys.stderr)
    print("📝 Event ID: {0}".format(getattr(cloud_event, 'id', 'unknown')), file=sys.stderr)
    print("📝 Event Type: {0}".format(getattr(cloud_event, 'type', 'unknown')), file=sys.stderr)
    print("📦 Event data:", json.dumps(cloud_event.data, indent=2), file=sys.stderr)
    
    try:
        # Extract document path information
        path_parts = cloud_event.data["value"]["name"].split("/documents/")[1].split("/")
        collection_path = path_parts[0]
        document_path = "/".join(path_parts[1:])
        
        print(f"📄 Processing change for: {collection_path}/{document_path}", file=sys.stderr)
        
        if collection_path != "users":
            print("⏭️ Skipping - not a user document change", file=sys.stderr)
            return

        user_id = path_parts[1]
        print(f"👤 User ID: {user_id}", file=sys.stderr)
        
        # Extract changed document fields
        if "fields" not in cloud_event.data["value"]:
            print("❌ No fields found in document change", file=sys.stderr)
            return

        changed_data = cloud_event.data["value"]["fields"]
        print("🔄 Document fields:", json.dumps(changed_data, indent=2), file=sys.stderr)
        
        # Check if notification preferences were updated
        update_mask = cloud_event.data.get("updateMask", {}).get("fieldPaths", [])
        notification_prefs_updated = 'notification_preferences' in update_mask
        print(f"🔄 Updated fields: {update_mask}", file=sys.stderr)
        if notification_prefs_updated:
            print("✅ Notification preferences were updated", file=sys.stderr)
        else:
            print("⏭️ Notification preferences not updated", file=sys.stderr)
        
        # Fetch user document from Firestore to get current state
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            print(f"❌ User document {user_id} not found", file=sys.stderr)
            return
        
        user_data = user_doc.to_dict()
        print(f"📋 User data retrieved: {user_data.get('name', 'Unknown user')}", file=sys.stderr)
        
        # Check FCM token
        fcm_token = user_data.get('fcm_token')
        if not fcm_token:
            print(f"❌ No FCM token found for user {user_id}", file=sys.stderr)
            return
        
        print(f"📱 Found FCM token: {fcm_token[:10]}...", file=sys.stderr)
        
        # Check if notifications are enabled
        notification_prefs = user_data.get('notification_preferences', {})
        is_enabled = notification_prefs.get('is_enabled', False)
        
        if not is_enabled:
            print(f"⏭️ Notifications are disabled for user {user_id}", file=sys.stderr)
            # Cancel any scheduled notifications
            cancel_user_notifications(user_id)
            return
        
        # Get notification time parameters
        hour = notification_prefs.get('hour')
        minute = notification_prefs.get('minute')
        
        if hour is None or minute is None:
            print(f"❌ Invalid notification time: hour={hour}, minute={minute}", file=sys.stderr)
            return
            
        # Calculate the next notification time
        now = datetime.now(timezone.utc)
        next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If the time has already passed today, schedule for tomorrow
        if next_time <= now:
            next_time = next_time + timedelta(days=1)
            
        print(f"⏰ Next notification time: {next_time.isoformat()}", file=sys.stderr)
        
        # Cancel any existing scheduled notifications
        cancel_user_notifications(user_id)
        
        # Schedule the next notification using Cloud Tasks
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
            
            print(f"✅ Successfully scheduled notification for {user_id} at {next_time.isoformat()}", file=sys.stderr)
            
        except Exception as schedule_error:
            print(f"❌ Error scheduling notification: {str(schedule_error)}", file=sys.stderr)
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", file=sys.stderr)
        import traceback
        print("📋 Stack trace:", traceback.format_exc(), file=sys.stderr)

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
            'updated_at': admin_firestore.SERVER_TIMESTAMP,
            'cancelled_reason': 'User updated notification preferences'
        })
        
        # If we have task_name, try to delete the Cloud Task
        if task_name:
            try:
                from google.cloud import tasks_v2
                client = tasks_v2.CloudTasksClient()
                client.delete_task(name=task_name)
                print(f"✅ Deleted Cloud Task: {task_name}", file=sys.stderr)
            except Exception as e:
                print(f"⚠️ Error deleting Cloud Task {task_name}: {str(e)}", file=sys.stderr)
        
        cancelled_count += 1
    
    print(f"📊 Cancelled {cancelled_count} notifications for user {user_id}", file=sys.stderr)

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
    
    print(f"🔄 Calling schedule_notification with payload: {payload}", file=sys.stderr)
    
    # Make the HTTP request
    response = requests.post(url, json=payload)
    
    # Process the response
    if response.status_code == 200:
        return response.json()
    else:
        error_message = f"Failed to schedule notification: {response.text}"
        print(f"❌ {error_message}", file=sys.stderr)
        raise Exception(error_message)