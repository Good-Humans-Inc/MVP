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
import re

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

def hex_dump(data, length=500):
    """Create a hexdump of binary data for debugging."""
    if not isinstance(data, bytes):
        return f"Not bytes: {data}"
    hex_str = binascii.hexlify(data[:length]).decode('ascii')
    chunks = [hex_str[i:i+2] for i in range(0, len(hex_str), 2)]
    formatted = ' '.join(chunks)
    return formatted

def extract_document_path_from_binary(data):
    """Extract the document path from binary data."""
    # Look for the document path format in the binary data
    if not isinstance(data, bytes):
        return None
    
    # Convert to text to search for the path
    try:
        text = data.decode('utf-8', errors='ignore')
        # Look for path pattern
        match = re.search(r'(projects/[^/]+/databases/[^/]+/documents/users/[a-zA-Z0-9-]+)', text)
        if match:
            return match.group(1)
    except:
        pass
    return None

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
        
        # Direct approach with binary data
        if isinstance(cloud_event.data, bytes):
            print(f"🔍 Binary data length: {len(cloud_event.data)} bytes", file=sys.stderr)
            print(f"🔍 Binary data hex dump: {hex_dump(cloud_event.data)}", file=sys.stderr)
            
            # Extract document path directly from binary data
            doc_path = extract_document_path_from_binary(cloud_event.data)
            if doc_path:
                print(f"✅ Extracted document path from binary: {doc_path}", file=sys.stderr)
                
                # Extract user_id from the path
                if '/users/' in doc_path:
                    user_id = doc_path.split('/users/')[1]
                    print(f"✅ Extracted user_id: {user_id}", file=sys.stderr)
                    
                    # Process user notification update
                    process_user_notification_update(user_id)
                    return
                else:
                    print(f"❌ Not a user document path: {doc_path}", file=sys.stderr)
                    return
            
            # Try to look for user ID directly in binary data
            try:
                text = cloud_event.data.decode('utf-8', errors='ignore')
                # Look for common UUID format often used for user IDs
                user_id_match = re.search(r'users/([a-zA-Z0-9-]{36})', text)
                if user_id_match:
                    user_id = user_id_match.group(1)
                    print(f"✅ Extracted user_id from binary text: {user_id}", file=sys.stderr)
                    
                    # Process user notification update
                    process_user_notification_update(user_id)
                    return
            except Exception as text_error:
                print(f"❌ Error extracting user_id from binary text: {str(text_error)}", file=sys.stderr)
        
        # Try various approaches to parse the data
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
            
            # Try to decode as UTF-8 JSON
            try:
                json_str = cloud_event.data.decode('utf-8')
                event_data = json.loads(json_str)
                print("✅ Successfully decoded as UTF-8 JSON", file=sys.stderr)
            except Exception as e:
                print(f"❌ Not UTF-8 JSON: {str(e)}", file=sys.stderr)
                
                # Try to parse as protocol buffer
                try:
                    # Use the Struct message to parse arbitrary JSON-like data
                    struct = Struct()
                    struct.ParseFromString(cloud_event.data)
                    event_data = json_format.MessageToDict(struct)
                    print(f"✅ Successfully parsed as protobuf Struct: {list(event_data.keys() if isinstance(event_data, dict) else [])}", file=sys.stderr)
                    
                    # Look for document path in the Struct
                    if isinstance(event_data, dict):
                        # Try to find the document path in the parsed struct
                        doc_path = None
                        # Look for keys that might contain the document path
                        for key in event_data.keys():
                            value = event_data[key]
                            if isinstance(value, str) and 'projects/' in value and '/users/' in value:
                                doc_path = value
                                break
                        
                        if doc_path:
                            print(f"✅ Found document path in parsed struct: {doc_path}", file=sys.stderr)
                            # Extract user_id from the path
                            user_id = doc_path.split('/users/')[1]
                            print(f"✅ Extracted user_id from struct: {user_id}", file=sys.stderr)
                            
                            # Process user notification update
                            process_user_notification_update(user_id)
                            return
                except Exception as pb_error:
                    print(f"❌ Error with protobuf Struct: {str(pb_error)}", file=sys.stderr)
                    
                # Try base64 decoding
                try:
                    decoded = base64.b64decode(cloud_event.data)
                    try:
                        json_str = decoded.decode('utf-8')
                        event_data = json.loads(json_str)
                        print("✅ Successfully decoded as base64 UTF-8 JSON", file=sys.stderr)
                    except Exception:
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
                    
                    # Process user notification update
                    process_user_notification_update(user_id)
                    return
        
        # If we have event data now, try to process it
        if event_data:
            print(f"✅ Successfully parsed event data, keys: {list(event_data.keys()) if isinstance(event_data, dict) else []}", file=sys.stderr)
            
            # Additional debugging
            if isinstance(event_data, dict):
                for key, value in event_data.items():
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    print(f"🔍 Event data[{key}] = {value_str}", file=sys.stderr)
            
            # Check for value field or look for document path
            if isinstance(event_data, dict):
                # Look for document path in the data
                doc_path = None
                
                # Check for common fields that might contain the document path
                if "value" in event_data and isinstance(event_data["value"], dict) and "name" in event_data["value"]:
                    doc_path = event_data["value"]["name"]
                elif "name" in event_data:
                    doc_path = event_data["name"]
                else:
                    # Look for any field containing the string '/users/'
                    for key, value in event_data.items():
                        if isinstance(value, str) and '/users/' in value:
                            doc_path = value
                            break
                
                if doc_path:
                    print(f"📄 Found document path: {doc_path}", file=sys.stderr)
                    
                    # Extract user_id from the path
                    if '/users/' in doc_path:
                        user_id = doc_path.split('/users/')[1]
                        print(f"✅ Extracted user_id from path: {user_id}", file=sys.stderr)
                        
                        # Process user notification update
                        process_user_notification_update(user_id)
                        return
                    else:
                        print(f"❌ Not a user document path: {doc_path}", file=sys.stderr)
                else:
                    print("❌ No document path found in parsed data", file=sys.stderr)
            else:
                print(f"❌ Parsed data is not a dictionary: {type(event_data)}", file=sys.stderr)
        
        # If we got here, we couldn't find or process the data
        print("❌ Failed to extract user ID from event data", file=sys.stderr)
            
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
        
        print(f"🕘 Notification preferences: hour={hour}, minute={minute}", file=sys.stderr)
        
        if hour is None or minute is None:
            print(f"❌ Invalid notification time: hour={hour}, minute={minute}", file=sys.stderr)
            return
        
        # Determine user's timezone by inspecting existing timestamps
        user_timezone_offset = None
        timezone_indicators = ['last_updated', 'last_token_update', 'updated_at', 'next_notification_time']
        
        for field in timezone_indicators:
            if field in user_data and user_data[field]:
                timestamp_value = user_data[field]
                # Check if the timestamp has timezone information
                if hasattr(timestamp_value, 'tzinfo') and timestamp_value.tzinfo:
                    user_timezone_offset = timestamp_value.utcoffset().total_seconds() / 3600
                    print(f"✅ Found user timezone offset: UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}", file=sys.stderr)
                    break
        
        # Default to UTC if we couldn't determine timezone
        if user_timezone_offset is None:
            print(f"⚠️ Could not determine user timezone, defaulting to UTC", file=sys.stderr)
            user_timezone_offset = 0
        
        # Convert hour to int to ensure proper handling
        try:
            hour = int(hour)
            minute = int(minute)
        except (ValueError, TypeError):
            print(f"❌ Could not convert hour/minute to integers: hour={hour}, minute={minute}", file=sys.stderr)
            return
        
        # Calculate the next notification time in UTC
        now = datetime.now(timezone.utc)
        print(f"🕒 Current time (UTC): {now.isoformat()}", file=sys.stderr)
        
        # Create a time in the user's timezone first
        user_hour_in_utc = hour - user_timezone_offset
        print(f"🕒 User's {hour}:{minute} in their timezone is {user_hour_in_utc}:{minute} in UTC", file=sys.stderr)
        
        # Calculate next notification time in UTC based on user's preferred local time
        next_time = now.replace(hour=int(user_hour_in_utc) % 24, minute=minute, second=0, microsecond=0)
        if int(user_hour_in_utc) < 0:
            # Handle case where user timezone pushes hour to previous day
            next_time = next_time + timedelta(days=1)
        elif int(user_hour_in_utc) >= 24:
            # Handle case where user timezone pushes hour to next day
            next_time = next_time - timedelta(days=1)
            
        print(f"🕒 Initial calculated time (UTC): {next_time.isoformat()}", file=sys.stderr)
        
        # If the time has already passed today, schedule for tomorrow
        if next_time <= now:
            next_time = next_time + timedelta(days=1)
            print(f"⏭️ Time today has passed, scheduling for tomorrow: {next_time.isoformat()}", file=sys.stderr)
        
        print(f"⏰ Calculated next notification time in UTC: {next_time.isoformat()}", file=sys.stderr)
        
        # Calculate what this time would be in the user's timezone (for logging only)
        user_local_time = next_time.astimezone(timezone(timedelta(hours=user_timezone_offset)))
        print(f"⏰ This equals {user_local_time.strftime('%Y-%m-%d %H:%M:%S')} in user's local timezone (UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset})", file=sys.stderr)
        
        # Check if this is just a preferences update without changing the time
        # If the existing time is still in the future, keep it
        existing_next_time = user_data.get('next_notification_time')
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
        
        print(f"⏰ Final next notification time (UTC): {next_time.isoformat()}", file=sys.stderr)
        
        # Cancel any existing scheduled notifications
        cancel_user_notifications(user_id)
        
        # Schedule the next notification
        try:
            # Convert datetime to ISO string for the API call
            next_time_iso = next_time.isoformat()
            print(f"📡 Sending scheduled_time to API: {next_time_iso}", file=sys.stderr)
            
            # Debug log the full payload
            debug_payload = {
                'user_id': user_id,
                'scheduled_time': next_time_iso,
                'is_one_time': False
            }
            print(f"📦 Full API payload: {json.dumps(debug_payload)}", file=sys.stderr)
            
            response_data = schedule_notification(
                user_id=user_id,
                scheduled_time=next_time_iso,
                is_one_time=False
            )
            
            # Debug the API response
            print(f"📡 Schedule API response details: {json.dumps(response_data) if response_data else 'None'}", file=sys.stderr)
            
            # Check if we got back a task_name and scheduled_for in the response
            if isinstance(response_data, dict):
                if 'scheduled_for' in response_data:
                    print(f"📅 API scheduled time: {response_data['scheduled_for']}", file=sys.stderr)
                if 'task_name' in response_data:
                    print(f"🔑 Task name: {response_data['task_name']}", file=sys.stderr)
            
            # Update the user's next notification time
            try:
                user_ref.update({
                    'next_notification_time': next_time
                })
                print(f"✅ Updated user's next_notification_time to {next_time.isoformat()}", file=sys.stderr)
            except Exception as update_error:
                print(f"❌ Error updating user's next_notification_time: {str(update_error)}", file=sys.stderr)
            
            print(f"✅ Successfully scheduled notification for {user_id} at {next_time.isoformat()} UTC", file=sys.stderr)
            print(f"✅ This will be {hour}:{minute:02d} in the user's local timezone", file=sys.stderr)
            
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