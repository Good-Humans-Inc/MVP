# monitor_notification_changes/main.py
import functions_framework
# Firebase Admin imports for database operations
import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore
from firebase_admin import messaging

# Import core protobuf library
import google.protobuf.json_format as json_format
from google.protobuf.struct_pb2 import Struct

import json
import requests
from datetime import datetime, timedelta, timezone
import uuid
import sys
import base64

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
    print(f"📝 Event ID: {getattr(cloud_event, 'id', 'unknown')}", file=sys.stderr)
    print(f"📝 Event Type: {getattr(cloud_event, 'type', 'unknown')}", file=sys.stderr)
    
    try:
        # Process event data
        event_data = {}
        if isinstance(cloud_event.data, bytes):
            # Handle binary protobuf data
            print(f"📦 Received binary data of length: {len(cloud_event.data)} bytes", file=sys.stderr)
            try:
                # First try to extract as base64
                try:
                    # Try to decode the protobuf data directly to string first
                    decoded_data = cloud_event.data.decode('utf-8')
                    if decoded_data.startswith('{'):
                        # This is actually JSON, not binary
                        event_data = json.loads(decoded_data)
                        print("✅ Decoded binary as UTF-8 JSON", file=sys.stderr)
                    else:
                        # It's not JSON, treat as binary
                        raise ValueError("Not JSON data")
                except (UnicodeDecodeError, ValueError):
                    # Direct binary protobuf - parse using protobuf library
                    struct = Struct()
                    struct.ParseFromString(cloud_event.data)
                    event_data = json_format.MessageToDict(struct)
                    print("✅ Parsed binary data using protobuf Struct", file=sys.stderr)
            except Exception as parse_error:
                # If that fails, try base64 encoding the binary data and print it
                encoded_data = base64.b64encode(cloud_event.data).decode('utf-8')
                print(f"⚠️ Could not parse binary data: {str(parse_error)}", file=sys.stderr)
                print(f"📦 Base64 encoded data: {encoded_data[:200]}...", file=sys.stderr)
                
                # Try a different approach - the Firestore document details
                # should be available in the cloud_event attributes
                event_subject = getattr(cloud_event, 'subject', '')
                print(f"📝 Event subject: {event_subject}", file=sys.stderr)
                
                # Extract collection and document ID from subject
                # Format is typically projects/_/databases/(default)/documents/{collection}/{doc_id}
                if '/documents/' in event_subject:
                    path_parts = event_subject.split('/documents/')[1].split('/')
                    if len(path_parts) >= 2:
                        collection_path = path_parts[0]
                        document_id = path_parts[1]
                        print(f"📄 Extracted from subject: {collection_path}/{document_id}", file=sys.stderr)
                        
                        # Continue processing with this information
                        if collection_path == 'users':
                            user_id = document_id
                            # Skip to processing the user document directly
                            process_user_notification_update(user_id)
                            return
                
                # If we got this far, we couldn't get the data we need
                print("❌ Could not extract necessary document information", file=sys.stderr)
                return
        else:
            # It's already a dictionary or string
            if isinstance(cloud_event.data, str):
                try:
                    event_data = json.loads(cloud_event.data)
                    print("✅ Parsed string data as JSON", file=sys.stderr)
                except json.JSONDecodeError:
                    print("❌ Could not parse string data as JSON", file=sys.stderr)
                    return
            else:
                event_data = cloud_event.data
                print("✅ Using dictionary data directly", file=sys.stderr)
        
        # Check for value field containing document info
        if not event_data or 'value' not in event_data:
            # Try another approach - check for alternative structure
            print("⚠️ No 'value' field in event data, checking alternative fields", file=sys.stderr)
            
            # Check various possible field structures
            document_path = None
            if 'document' in event_data:
                document_path = event_data.get('document', {}).get('name')
            elif 'resource' in event_data:
                document_path = event_data.get('resource', {}).get('name')
            
            if not document_path:
                # As a last resort, try to extract from the event subject
                event_subject = getattr(cloud_event, 'subject', '')
                if '/documents/' in event_subject:
                    document_path = event_subject
            
            if not document_path:
                print("❌ Could not find document path in event data", file=sys.stderr)
                return
        else:
            document_path = event_data.get('value', {}).get('name')
        
        # Extract collection and document ID from path
        if '/documents/' not in document_path:
            print(f"❌ Invalid document path format: {document_path}", file=sys.stderr)
            return
            
        path_parts = document_path.split('/documents/')[1].split('/')
        if len(path_parts) < 2:
            print(f"❌ Invalid document path format: {document_path}", file=sys.stderr)
            return
            
        collection_path = path_parts[0]
        document_id = path_parts[1]
        
        print(f"📄 Processing change for: {collection_path}/{document_id}", file=sys.stderr)
        
        if collection_path != "users":
            print("⏭️ Skipping - not a user document change", file=sys.stderr)
            return
        
        # Process the user document
        user_id = document_id
        process_user_notification_update(user_id)
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", file=sys.stderr)
        import traceback
        print("📋 Stack trace:", traceback.format_exc(), file=sys.stderr)

def process_user_notification_update(user_id):
    """Process a user document update to schedule notifications."""
    print(f"👤 Processing notification update for user ID: {user_id}", file=sys.stderr)
    
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