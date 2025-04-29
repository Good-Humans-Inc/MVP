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
    """Triggered by a change to a Firestore document."""
    print("🔔 FUNCTION TRIGGERED - STARTING EXECUTION", file=sys.stderr)
    
    # Print detailed cloud_event information
    print(f"📝 Event ID: {getattr(cloud_event, 'id', 'unknown')}", file=sys.stderr)
    print(f"📝 Event Type: {getattr(cloud_event, 'type', 'unknown')}", file=sys.stderr)
    print(f"📝 Source: {getattr(cloud_event, 'source', 'unknown')}", file=sys.stderr)
    print(f"📝 Subject: {getattr(cloud_event, 'subject', 'unknown')}", file=sys.stderr)
    print(f"📝 Time: {getattr(cloud_event, 'time', 'unknown')}", file=sys.stderr)
    print(f"📝 Content Type: {getattr(cloud_event, 'data_content_type', 'unknown')}", file=sys.stderr)
    
    # Print all attributes
    print("📝 All attributes:", file=sys.stderr)
    for attr in dir(cloud_event):
        if not attr.startswith('_') and attr != 'data':
            print(f"   {attr}: {getattr(cloud_event, attr, 'N/A')}", file=sys.stderr)
    
    try:
        # Process event data
        event_data = {}
        if isinstance(cloud_event.data, bytes):
            # Handle binary protobuf data
            print(f"📦 Received binary data of length: {len(cloud_event.data)} bytes", file=sys.stderr)
            print(f"📦 Hex dump of first 100 bytes: {hex_dump(cloud_event.data)}", file=sys.stderr)
            
            # Base64 encode for easier debugging
            encoded_data = base64.b64encode(cloud_event.data).decode('utf-8')
            print(f"📦 Full Base64 encoded data: {encoded_data}", file=sys.stderr)
            
            try:
                # Try to decode the protobuf data directly to string first
                try:
                    decoded_data = cloud_event.data.decode('utf-8')
                    print(f"📦 Decoded as UTF-8 (first 200 chars): {decoded_data[:200]}", file=sys.stderr)
                    if decoded_data.startswith('{'):
                        # This is actually JSON, not binary
                        event_data = json.loads(decoded_data)
                        print("✅ Decoded binary as UTF-8 JSON", file=sys.stderr)
                    else:
                        # It's not JSON, treat as binary
                        raise ValueError("Not JSON data")
                except (UnicodeDecodeError, ValueError):
                    print("⚠️ Not UTF-8 encoded text, trying protobuf parsing", file=sys.stderr)
                    
                    # Try different protobuf message types
                    try:
                        # Generic Struct
                        struct = Struct()
                        struct.ParseFromString(cloud_event.data)
                        event_data = json_format.MessageToDict(struct)
                        print("✅ Parsed binary data using protobuf Struct", file=sys.stderr)
                    except Exception as e1:
                        print(f"⚠️ Failed to parse as Struct: {str(e1)}", file=sys.stderr)
                        
                        # Try as FileDescriptorSet (for schema info)
                        try:
                            fd_set = descriptor_pb2.FileDescriptorSet()
                            fd_set.ParseFromString(cloud_event.data)
                            print(f"✅ Parsed as FileDescriptorSet with {len(fd_set.file)} files", file=sys.stderr)
                            
                            # Create a descriptor pool from the descriptors
                            pool = DescriptorPool()
                            for fd in fd_set.file:
                                pool.Add(fd)
                            
                            # Print the message types
                            for fd in fd_set.file:
                                for msg_type in fd.message_type:
                                    print(f"📝 Found message type: {fd.package}.{msg_type.name}", file=sys.stderr)
                        except Exception as e2:
                            print(f"⚠️ Failed to parse as FileDescriptorSet: {str(e2)}", file=sys.stderr)
                            
                            # Look for common patterns in the binary data
                            try:
                                # Convert to hex for searching
                                hex_data = binascii.hexlify(cloud_event.data).decode('ascii')
                                
                                # Look for document path patterns - convert common strings to hex and search
                                doc_pattern = binascii.hexlify(b"documents").decode('ascii')
                                users_pattern = binascii.hexlify(b"users").decode('ascii')
                                
                                if doc_pattern in hex_data:
                                    print(f"📦 Found 'documents' pattern in binary data", file=sys.stderr)
                                if users_pattern in hex_data:
                                    print(f"📦 Found 'users' pattern in binary data", file=sys.stderr)
                                    
                                # Try to extract strings from the binary data
                                def extract_strings(data, min_length=4):
                                    result = []
                                    current = ""
                                    for byte in data:
                                        if 32 <= byte <= 126:  # printable ASCII
                                            current += chr(byte)
                                        else:
                                            if len(current) >= min_length:
                                                result.append(current)
                                            current = ""
                                    if len(current) >= min_length:
                                        result.append(current)
                                    return result
                                
                                strings = extract_strings(cloud_event.data)
                                print(f"📦 Extracted strings from binary: {strings[:20]}", file=sys.stderr)
                                
                                # Try to find document paths in extracted strings
                                for s in strings:
                                    if 'documents' in s and 'users' in s:
                                        print(f"📦 Potential document path: {s}", file=sys.stderr)
                                        parts = s.split('users/')
                                        if len(parts) > 1 and len(parts[1]) > 0:
                                            user_id = parts[1].split('/')[0]
                                            print(f"📄 Extracted user ID: {user_id}", file=sys.stderr)
                                            process_user_notification_update(user_id)
                                            return
                            except Exception as e3:
                                print(f"⚠️ Failed pattern analysis: {str(e3)}", file=sys.stderr)
                            
            except Exception as parse_error:
                print(f"⚠️ Could not parse binary data: {str(parse_error)}", file=sys.stderr)
                  
            # Extract from subject as last resort
            event_subject = getattr(cloud_event, 'subject', '')
            print(f"📝 Event subject: {event_subject}", file=sys.stderr)
            
            # Try to extract from source
            event_source = getattr(cloud_event, 'source', '')
            print(f"📝 Event source: {event_source}", file=sys.stderr)
            
            # Check various fields in attributes
            try:
                # Check if any attributes might contain document path
                if hasattr(cloud_event, 'attributes'):
                    print("📝 Checking cloud_event attributes:", file=sys.stderr)
                    attrs = getattr(cloud_event, 'attributes', {})
                    for key, value in attrs.items():
                        print(f"   {key}: {value}", file=sys.stderr)
                        if 'document' in str(value) or 'users' in str(value):
                            print(f"📄 Potential document info in attribute {key}: {value}", file=sys.stderr)
            except Exception as attr_error:
                print(f"⚠️ Error checking attributes: {str(attr_error)}", file=sys.stderr)
            
            # Try to parse the event type for clues
            event_type = getattr(cloud_event, 'type', '')
            if event_type and 'firestore' in event_type:
                print(f"📝 Analyzing Firestore event type: {event_type}", file=sys.stderr)
                
                # Many Firestore events include IDs in the subject or directly in the type
                parts = event_type.split('.')
                if len(parts) > 1:
                    last_part = parts[-1]
                    print(f"📝 Event type last part: {last_part}", file=sys.stderr)
                    
            if not event_subject and not event_source:
                # Last attempt - check the hex data for known patterns
                for known_id in db.collection('users').stream():
                    user_id = known_id.id
                    if user_id.encode('utf-8') in cloud_event.data:
                        print(f"📄 Found user ID in binary data: {user_id}", file=sys.stderr)
                        process_user_notification_update(user_id)
                        return
                
                # If we got this far, we couldn't get the data we need
                print("❌ Could not extract necessary document information", file=sys.stderr)
                return
        else:
            # It's already a dictionary or string
            if isinstance(cloud_event.data, str):
                print(f"📄 Received string data (first 200 chars): {cloud_event.data[:200]}", file=sys.stderr)
                try:
                    event_data = json.loads(cloud_event.data)
                    print("✅ Parsed string data as JSON", file=sys.stderr)
                except json.JSONDecodeError:
                    print("❌ Could not parse string data as JSON", file=sys.stderr)
                    return
            else:
                event_data = cloud_event.data
                print("✅ Using dictionary data directly", file=sys.stderr)
        
        # Dump event data for debugging
        if event_data:
            try:
                print(f"📦 Event data sample: {json.dumps(event_data)[:500]}...", file=sys.stderr)
            except:
                print("⚠️ Could not JSON dump event_data", file=sys.stderr)
        
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