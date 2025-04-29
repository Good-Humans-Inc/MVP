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
import binascii

# For parsing protobuf messages
import google.protobuf.json_format as json_format
from google.protobuf.struct_pb2 import Struct
from google.protobuf import descriptor_pb2
from google.protobuf.descriptor_pool import DescriptorPool

# Initialize Firebase Admin
try:
    app = firebase_admin.initialize_app()
except ValueError:
    app = firebase_admin.get_app()

# Create Firestore client
db = admin_firestore.Client(project='pepmvp', database='pep-mvp')

def hex_dump(data, length=250):
    """Create a hexdump of binary data for debugging."""
    if not isinstance(data, bytes):
        return f"Not bytes: {data}"
    hex_str = binascii.hexlify(data[:length]).decode('ascii')
    chunks = [hex_str[i:i+2] for i in range(0, len(hex_str), 2)]
    formatted = ' '.join(chunks)
    return formatted

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
        
        # Debug cloud event properties
        print(f"🔍 Cloud Event Type: {cloud_event.type if hasattr(cloud_event, 'type') else 'unknown'}", file=sys.stderr)
        print(f"🔍 Cloud Event Subject: {cloud_event.subject if hasattr(cloud_event, 'subject') else 'unknown'}", file=sys.stderr)
        print(f"🔍 Cloud Event ID: {cloud_event.id if hasattr(cloud_event, 'id') else 'unknown'}", file=sys.stderr)
        print(f"🔍 Cloud Event Data Type: {type(cloud_event.data)}", file=sys.stderr)
        
        # Handle binary data - try different approaches
        event_data = None
        
        if isinstance(cloud_event.data, dict):
            # Already a dict
            event_data = cloud_event.data
            print("✅ Data is already a dictionary", file=sys.stderr)
        elif isinstance(cloud_event.data, str):
            # Try parsing as JSON string
            try:
                event_data = json.loads(cloud_event.data)
                print("✅ Successfully parsed data as JSON string", file=sys.stderr)
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse as JSON string: {str(e)}", file=sys.stderr)
        elif isinstance(cloud_event.data, bytes):
            # Try different approaches for binary data
            print(f"🔍 Binary data length: {len(cloud_event.data)} bytes", file=sys.stderr)
            print(f"🔍 Binary data hex dump: {hex_dump(cloud_event.data)}", file=sys.stderr)
            
            # Try to decode as UTF-8 JSON
            try:
                json_str = cloud_event.data.decode('utf-8')
                event_data = json.loads(json_str)
                print("✅ Successfully decoded as UTF-8 JSON", file=sys.stderr)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"❌ Not UTF-8 JSON: {str(e)}", file=sys.stderr)
                
                # Try to parse as protocol buffer
                try:
                    # Use the Struct message to parse arbitrary JSON-like data
                    struct = Struct()
                    struct.ParseFromString(cloud_event.data)
                    event_data = json_format.MessageToDict(struct)
                    print("✅ Successfully parsed as protobuf Struct", file=sys.stderr)
                except Exception as pb_error:
                    print(f"❌ Not a protobuf Struct: {str(pb_error)}", file=sys.stderr)
                    
                    # Try base64 decoding
                    try:
                        decoded = base64.b64decode(cloud_event.data)
                        try:
                            json_str = decoded.decode('utf-8')
                            event_data = json.loads(json_str)
                            print("✅ Successfully decoded as base64 UTF-8 JSON", file=sys.stderr)
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            print("❌ Base64 decoded data is not UTF-8 JSON", file=sys.stderr)
                    except Exception as b64_error:
                        print(f"❌ Not base64 encoded: {str(b64_error)}", file=sys.stderr)
        
        # If all parsing attempts failed, try the raw event
        if event_data is None:
            print("⚠️ All parsing attempts failed, trying to extract fields directly from the event", file=sys.stderr)
            # Get attributes from the cloud event
            if hasattr(cloud_event, 'attributes') and cloud_event.attributes:
                print(f"🔍 Event attributes: {cloud_event.attributes}", file=sys.stderr)
                
                # Extract resource name from attributes if possible
                resource_name = None
                if 'resource' in cloud_event.attributes:
                    resource_name = cloud_event.attributes['resource']
                    print(f"🔍 Resource name from attributes: {resource_name}", file=sys.stderr)
                
                # If we found a resource name, try to process it
                if resource_name and '/users/' in resource_name:
                    # Extract user_id from the resource name
                    user_id = resource_name.split('/users/')[1]
                    print(f"✅ Extracted user_id from attributes: {user_id}", file=sys.stderr)
                    
                    # Process the user notification update
                    process_user_notification_update(user_id)
                    return
        
        # If we have event data now, try to process it
        if event_data:
            print(f"✅ Successfully parsed event data, keys: {list(event_data.keys())}", file=sys.stderr)
            
            # Additional debugging
            if isinstance(event_data, dict):
                for key, value in event_data.items():
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    print(f"🔍 Event data[{key}] = {value_str}", file=sys.stderr)
            
            # Check for "value" field in parsed data
            if "value" not in event_data:
                print("❌ No 'value' field in parsed event data", file=sys.stderr)
                return
                
            event_value = event_data.get("value", {})
            if not isinstance(event_value, dict):
                print(f"❌ 'value' is not a dictionary, got {type(event_value)}", file=sys.stderr)
                return
                
            # Check if we have update mask to determine if relevant fields were changed
            update_mask = event_data.get("updateMask", {})
            field_paths = update_mask.get("fieldPaths", []) if isinstance(update_mask, dict) else []
            
            print(f"🔍 Update Mask Field Paths: {field_paths}", file=sys.stderr)
            
            # Check if relevant fields were updated
            relevant_fields = ["notification_preferences", "next_notification_time"]
            field_updated = False
            
            # If no specific fields are listed, assume all fields were updated
            if not field_paths:
                field_updated = True
                print("✅ No specific fields listed in update mask, processing update", file=sys.stderr)
            else:
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
            
            # Extract user_id from path
            # Path format: projects/{project_id}/databases/{database}/documents/users/{user_id}
            if '/users/' not in resource_path:
                print(f"❌ Not a user document path: {resource_path}", file=sys.stderr)
                return
                
            # Extract user_id from the path
            user_id = resource_path.split('/users/')[1]
            if not user_id:
                print(f"❌ Could not extract user_id from path: {resource_path}", file=sys.stderr)
                return
            
            print(f"📄 Extracted User ID: {user_id}", file=sys.stderr)
            
            # Process user notification update
            process_user_notification_update(user_id)
        else:
            print("❌ Failed to parse event data using all available methods", file=sys.stderr)
            
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