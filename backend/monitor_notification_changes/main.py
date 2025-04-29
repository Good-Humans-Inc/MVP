# monitor_notification_changes/main.py
import functions_framework
# Firebase Admin imports for database operations
import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore
from firebase_admin import messaging

# Import core protobuf library
import google.protobuf.json_format as json_format
from google.protobuf.struct_pb2 import Struct
from google.protobuf import descriptor_pb2
from google.protobuf.descriptor_pool import DescriptorPool

import json
import requests
from datetime import datetime, timedelta, timezone
import uuid
import sys
import base64
import binascii

# Initialize Firebase Admin
try:
    app = firebase_admin.initialize_app()
except ValueError:
    app = firebase_admin.get_app()

# Create Firestore client - using the admin_firestore module
db = admin_firestore.Client(project='pepmvp', database='pep-mvp')

def hex_dump(data, length=100):
    """Create a hexdump of binary data for debugging."""
    hex_str = binascii.hexlify(data[:length]).decode('ascii')
    chunks = [hex_str[i:i+2] for i in range(0, len(hex_str), 2)]
    formatted = ' '.join(chunks)
    return formatted

@functions_framework.cloud_event
def monitor_notification_changes(cloud_event):
    """Entry point for the Cloud Function.
    Args:
        cloud_event: The CloudEvent that triggered this function.
    """
    print("🔄 Notification change detected", file=sys.stderr)
    
    try:
        # Extract the path from the event data
        resource_path = cloud_event.data["value"]["name"]
        print(f"📄 Resource path: {resource_path}", file=sys.stderr)
        
        # Extract document data
        document_data = None
        if "fields" in cloud_event.data["value"]:
            document_data = cloud_event.data["value"]["fields"]
        else:
            print("❌ No fields found in document data", file=sys.stderr)
            return
            
        # Extract collection and document ID from path
        # Path format: projects/{project_id}/databases/{database}/documents/{collection_id}/{document_id}
        path_parts = resource_path.split('/')
        if len(path_parts) >= 6:
            collection_id = path_parts[-2]
            document_id = path_parts[-1]
            
            print(f"📄 Collection: {collection_id}, Document: {document_id}", file=sys.stderr)
            
            # Only process notifications collection
            if collection_id != "notifications":
                print(f"⚠️ Ignoring change from collection: {collection_id}", file=sys.stderr)
                return
                
            # Check if notification is already being processed
            db = admin_firestore.Client()
            doc_ref = db.collection(collection_id).document(document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                doc_data = doc.to_dict()
                is_being_processed = doc_data.get("isBeingProcessed", False)
                
                if is_being_processed:
                    print(f"⚠️ Notification {document_id} is already being processed. Skipping.", file=sys.stderr)
                    return
                    
                # Mark notification as being processed
                doc_ref.update({"isBeingProcessed": True})
                
                try:
                    # Process the notification change
                    process_notification_change(document_id, document_data)
                finally:
                    # Reset the processing flag
                    try:
                        doc_ref.update({"isBeingProcessed": False})
                    except Exception as update_error:
                        print(f"❌ Failed to reset processing flag: {str(update_error)}", file=sys.stderr)
            else:
                print(f"⚠️ Document {document_id} no longer exists", file=sys.stderr)
        else:
            print(f"❌ Invalid path format: {resource_path}", file=sys.stderr)
    
    except Exception as e:
        print(f"❌ Error processing notification change: {str(e)}", file=sys.stderr)

def process_notification_change(notification_id, document_data):
    """Process changes to a notification document."""
    print(f"🔄 Processing notification {notification_id}", file=sys.stderr)
    
    try:
        # Extract the required fields from the document data
        if "user_id" not in document_data:
            print(f"❌ Missing user_id in notification {notification_id}", file=sys.stderr)
            return
            
        if "status" not in document_data:
            print(f"❌ Missing status in notification {notification_id}", file=sys.stderr)
            return
            
        user_id = document_data["user_id"]["stringValue"]
        status = document_data["status"]["stringValue"]
        
        print(f"📄 Processing notification for user: {user_id} with status: {status}", file=sys.stderr)
        
        # Initialize Firestore client
        db = admin_firestore.Client()
        
        # Check if this is a new or updated notification
        if status == "scheduled":
            # Check if there's a scheduled_time field
            if "scheduled_time" not in document_data:
                print(f"❌ Missing scheduled_time in notification {notification_id}", file=sys.stderr)
                return
                
            # Get the scheduled time
            scheduled_time_value = document_data["scheduled_time"]
            
            # Handle different Firestore value types
            if "timestampValue" in scheduled_time_value:
                # Parse the timestamp value
                timestamp_str = scheduled_time_value["timestampValue"]
                scheduled_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                print(f"❌ Invalid scheduled_time format in notification {notification_id}", file=sys.stderr)
                return
                
            # Get the notification data
            title = document_data.get("title", {}).get("stringValue", "Reminder")
            body = document_data.get("body", {}).get("stringValue", "")
            data = {}
            
            if "data" in document_data and "mapValue" in document_data["data"]:
                data_fields = document_data["data"]["mapValue"].get("fields", {})
                for key, value in data_fields.items():
                    # Extract value based on type
                    if "stringValue" in value:
                        data[key] = value["stringValue"]
                    elif "integerValue" in value:
                        data[key] = value["integerValue"]
                    elif "booleanValue" in value:
                        data[key] = value["booleanValue"]
            
            # Schedule the notification
            try:
                # Get any existing task name
                task_name = None
                if "task_name" in document_data and "stringValue" in document_data["task_name"]:
                    task_name = document_data["task_name"]["stringValue"]
                
                # If there's an existing task, cancel it first
                if task_name:
                    try:
                        cancel_notification(task_name)
                        print(f"✅ Cancelled existing task: {task_name}", file=sys.stderr)
                    except Exception as cancel_error:
                        print(f"⚠️ Error cancelling task {task_name}: {str(cancel_error)}", file=sys.stderr)
                
                # Schedule the new notification
                new_task_name = schedule_notification(
                    user_id=user_id,
                    notification_id=notification_id,
                    title=title,
                    body=body,
                    data=data,
                    scheduled_time=scheduled_time
                )
                
                # Update the notification with the new task name
                if new_task_name:
                    db.collection("notifications").document(notification_id).update({
                        "task_name": new_task_name,
                        "status": "scheduled"
                    })
                    print(f"✅ Scheduled notification with task: {new_task_name}", file=sys.stderr)
                
            except Exception as schedule_error:
                print(f"❌ Error scheduling notification: {str(schedule_error)}", file=sys.stderr)
                db.collection("notifications").document(notification_id).update({
                    "status": "error",
                    "error_message": str(schedule_error)
                })
        
        elif status == "cancelled":
            # Check if there's a task_name field
            if "task_name" in document_data and "stringValue" in document_data["task_name"]:
                task_name = document_data["task_name"]["stringValue"]
                
                try:
                    # Cancel the notification
                    cancel_notification(task_name)
                    print(f"✅ Cancelled notification task: {task_name}", file=sys.stderr)
                    
                    # Update the notification status
                    db.collection("notifications").document(notification_id).update({
                        "status": "cancelled"
                    })
                except Exception as cancel_error:
                    print(f"❌ Error cancelling notification: {str(cancel_error)}", file=sys.stderr)
                    db.collection("notifications").document(notification_id).update({
                        "status": "error",
                        "error_message": str(cancel_error)
                    })
            else:
                print(f"⚠️ No task_name found for cancelled notification {notification_id}", file=sys.stderr)
        
        # Process user's notification update
        process_user_notification_update(user_id)
        
    except Exception as e:
        print(f"❌ Error processing notification {notification_id}: {str(e)}", file=sys.stderr)
        # Update notification status to error
        try:
            db = admin_firestore.Client()
            db.collection("notifications").document(notification_id).update({
                "status": "error",
                "error_message": str(e)
            })
        except Exception as update_error:
            print(f"❌ Failed to update notification status: {str(update_error)}", file=sys.stderr)

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
    
    # Get the current notification time if already set
    existing_next_time = user_data.get('next_notification_time')
    if existing_next_time:
        if hasattr(existing_next_time, 'isoformat'):
            print(f"📅 Existing next notification time: {existing_next_time.isoformat()}", file=sys.stderr)
        else:
            print(f"📅 Existing next notification time: {existing_next_time}", file=sys.stderr)
    else:
        print("📅 No existing next notification time", file=sys.stderr)
    
    # Calculate the next notification time
    now = datetime.now(timezone.utc)
    next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If the time has already passed today, schedule for tomorrow
    if next_time <= now:
        next_time = next_time + timedelta(days=1)
        print(f"⏭️ Time today has passed, scheduling for tomorrow: {next_time.isoformat()}", file=sys.stderr)
    
    print(f"⏰ Calculated next notification time: {next_time.isoformat()}", file=sys.stderr)
    
    # Check if this is just a preferences update without changing the time
    # If the existing time is still in the future, keep it
    if existing_next_time:
        try:
            # Handle different datetime types
            if hasattr(existing_next_time, 'timestamp'):
                existing_time = datetime.fromtimestamp(existing_next_time.timestamp(), tz=timezone.utc)
            elif isinstance(existing_next_time, str):
                existing_time = datetime.fromisoformat(existing_next_time.replace('Z', '+00:00'))
            else:
                # If we can't parse it, use the calculated time
                raise ValueError("Unparseable datetime format")
                
            # If existing time is in the future, keep it
            if existing_time > now:
                print(f"🔄 Keeping existing notification time: {existing_time.isoformat()}", file=sys.stderr)
                next_time = existing_time
        except Exception as e:
            print(f"⚠️ Error parsing existing notification time: {str(e)}", file=sys.stderr)
            print(f"⚠️ Using calculated time instead", file=sys.stderr)
    
    print(f"⏰ Final next notification time: {next_time.isoformat()}", file=sys.stderr)
    
    # Cancel any existing scheduled notifications
    cancel_user_notifications(user_id)
    
    # Schedule the next notification using Cloud Tasks
    try:
        # Convert datetime to ISO string for the API call
        next_time_iso = next_time.isoformat()
        
        response_data = schedule_notification(
            user_id=user_id,
            scheduled_time=next_time_iso,
            is_one_time=False
        )
        
        # Update the user's next notification time
        try:
            user_ref.update({
                'next_notification_time': next_time
            })
            print(f"✅ Updated user's next_notification_time to {next_time.isoformat()}", file=sys.stderr)
        except Exception as update_error:
            print(f"❌ Error updating user's next_notification_time: {str(update_error)}", file=sys.stderr)
        
        print(f"✅ Successfully scheduled notification for {user_id} at {next_time.isoformat()}", file=sys.stderr)
        
    except Exception as schedule_error:
        print(f"❌ Error scheduling notification: {str(schedule_error)}", file=sys.stderr)
        # Try to log more details about the error
        import traceback
        print(f"📋 Schedule error traceback: {traceback.format_exc()}", file=sys.stderr)

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
    # Ensure scheduled_time is a string in ISO format
    if isinstance(scheduled_time, datetime):
        scheduled_time = scheduled_time.isoformat()
    
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
    
    try:
        # Make the HTTP request with a timeout
        response = requests.post(url, json=payload, timeout=30)
        
        # Process the response
        print(f"📡 Schedule API response status: {response.status_code}", file=sys.stderr)
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"✅ Schedule API success: {json.dumps(response_data)}", file=sys.stderr)
            return response_data
        else:
            error_message = f"Failed to schedule notification: HTTP {response.status_code}: {response.text}"
            print(f"❌ {error_message}", file=sys.stderr)
            
            # Try to parse the error response
            try:
                error_json = response.json()
                print(f"❌ Error details: {json.dumps(error_json)}", file=sys.stderr)
            except:
                print(f"❌ Could not parse error response as JSON", file=sys.stderr)
                
            raise Exception(error_message)
    except requests.exceptions.RequestException as req_error:
        error_message = f"Request error when calling schedule_notification: {str(req_error)}"
        print(f"❌ {error_message}", file=sys.stderr)
        raise Exception(error_message)