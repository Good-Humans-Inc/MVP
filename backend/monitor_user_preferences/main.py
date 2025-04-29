# monitor_user_preferences/main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore
import json
import requests
from datetime import datetime, timedelta, timezone
import sys
import traceback
import base64

# Initialize Firebase Admin
try:
    app = firebase_admin.initialize_app()
except ValueError:
    app = firebase_admin.get_app()

# Create Firestore client
db = admin_firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.cloud_event
def monitor_user_preferences(cloud_event):
    """Entry point for the Cloud Function.
    This function is triggered only when a user's notification_preferences or next_notification_time
    is updated in the Firestore database.
    
    Args:
        cloud_event: The CloudEvent that triggered this function.
    """
    print("🔄 User notification preferences change detected", file=sys.stderr)
    
    try:
        # Check if we have data in the cloud_event
        if not hasattr(cloud_event, 'data') or not cloud_event.data:
            print("❌ No data in cloud_event", file=sys.stderr)
            return
        
        # Handle binary data - convert to JSON object
        event_data = None
        try:
            # First, try parsing as JSON directly (might be a string)
            if isinstance(cloud_event.data, str):
                event_data = json.loads(cloud_event.data)
            # Next, try parsing as binary data
            elif isinstance(cloud_event.data, bytes):
                event_data = json.loads(cloud_event.data.decode('utf-8'))
            else:
                # If already a dict, use as is
                event_data = cloud_event.data
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"❌ Error decoding event data: {str(e)}", file=sys.stderr)
            print(f"❌ Data type: {type(cloud_event.data)}", file=sys.stderr)
            if isinstance(cloud_event.data, bytes):
                print(f"❌ First 100 bytes: {cloud_event.data[:100]}", file=sys.stderr)
            return
            
        if not event_data or not isinstance(event_data, dict):
            print(f"❌ Invalid event data format: {type(event_data)}", file=sys.stderr)
            return
            
        # Now safely process the event data
        if "value" not in event_data:
            print("❌ No 'value' field in event data", file=sys.stderr)
            return
            
        event_value = event_data.get("value", {})
        if not isinstance(event_value, dict):
            print(f"❌ 'value' is not a dictionary, got {type(event_value)}", file=sys.stderr)
            return
            
        # Check if we have update mask to determine if relevant fields were changed
        update_mask = event_data.get("updateMask", {})
        field_paths = update_mask.get("fieldPaths", []) if isinstance(update_mask, dict) else []
        
        # Check if relevant fields were updated
        relevant_fields = ["notification_preferences", "next_notification_time"]
        field_updated = False
        
        for field in relevant_fields:
            for updated_path in field_paths:
                # Check for exact match or path that starts with the field
                if updated_path == field or updated_path.startswith(f"{field}."):
                    field_updated = True
                    print(f"✅ Relevant field updated: {updated_path}", file=sys.stderr)
                    break
                    
            if field_updated:
                break
        
        # Skip processing if no relevant fields were updated
        if field_paths and not field_updated:
            print(f"⏭️ No relevant fields updated, fields updated: {field_paths}", file=sys.stderr)
            return
            
        # Extract document info
        resource_path = event_value.get("name")
        if not resource_path:
            print("❌ No 'name' field in event data value", file=sys.stderr)
            return
        
        print(f"📄 Resource path: {resource_path}", file=sys.stderr)
        
        # Extract document data
        if "fields" not in event_value:
            print("❌ No fields found in document data", file=sys.stderr)
            return
            
        # Extract user_id from path
        # Path format: projects/{project_id}/databases/{database}/documents/users/{user_id}
        path_parts = resource_path.split('/')
        if len(path_parts) < 6:
            print(f"❌ Invalid path format: {resource_path}", file=sys.stderr)
            return
            
        collection_id = path_parts[-2]
        user_id = path_parts[-1]
        
        print(f"📄 Collection: {collection_id}, User ID: {user_id}", file=sys.stderr)
        
        # Only process users collection
        if collection_id != "users":
            print(f"⚠️ Ignoring change from non-user collection: {collection_id}", file=sys.stderr)
            return
            
        # Process user notification update
        process_user_notification_update(user_id)
        
    except Exception as e:
        print(f"❌ Error processing user preference change: {str(e)}", file=sys.stderr)
        print(f"❌ Traceback: {traceback.format_exc()}", file=sys.stderr)

def process_user_notification_update(user_id):
    """Process a user document update to schedule notifications."""
    print(f"👤 Processing notification update for user ID: {user_id}", file=sys.stderr)
    
    try:
        # Fetch user document from Firestore
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
        
        # Schedule the next notification
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
            print(f"📋 Schedule error traceback: {traceback.format_exc()}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Error processing user notification update: {str(e)}", file=sys.stderr)
        print(f"📋 Error traceback: {traceback.format_exc()}", file=sys.stderr)

def cancel_user_notifications(user_id):
    """Cancel all scheduled notifications for a user."""
    print(f"🔄 Cancelling existing notifications for user {user_id}", file=sys.stderr)
    
    try:
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
    except Exception as e:
        print(f"❌ Error cancelling user notifications: {str(e)}", file=sys.stderr)
        print(f"📋 Error traceback: {traceback.format_exc()}", file=sys.stderr)

def schedule_notification(user_id, scheduled_time, is_one_time=False, custom_title=None, custom_body=None):
    """Call the schedule_notification Cloud Function to schedule a notification."""
    print(f"🔄 Scheduling notification for user {user_id}", file=sys.stderr)
    
    # Ensure scheduled_time is a string in ISO format
    if isinstance(scheduled_time, datetime):
        scheduled_time = scheduled_time.isoformat()
    
    payload = {
        'user_id': user_id,
        'scheduled_time': scheduled_time,
        'is_one_time': is_one_time
    }
    
    # Add custom content if provided
    if custom_title:
        payload['custom_title'] = custom_title
    
    if custom_body:
        payload['custom_body'] = custom_body
    
    # URL of the schedule_notification Cloud Function
    url = f"https://us-central1-pepmvp.cloudfunctions.net/schedule_notification"
    
    print(f"🔄 Calling schedule_notification with payload: {json.dumps(payload)}", file=sys.stderr)
    
    try:
        # Make the HTTP request with a timeout
        response = requests.post(url, json=payload, timeout=30)
        
        # Process the response
        print(f"📡 Schedule API response status: {response.status_code}", file=sys.stderr)
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                print(f"✅ Schedule API success: {json.dumps(response_data)}", file=sys.stderr)
                return response_data
            except json.JSONDecodeError:
                print(f"⚠️ Could not parse response as JSON: {response.text}", file=sys.stderr)
                return None
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