# monitor_notification_changes/main.py
import functions_framework
from firebase_admin import initialize_app, firestore
from firebase_admin import messaging
import json
import requests
from datetime import datetime, timedelta, timezone
import uuid
import sys

# Initialize Firebase Admin
try:
    app = initialize_app()
except ValueError:
    app = initialize_app()

db = firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.cloud_event
def monitor_notification_changes(cloud_event):
    """Triggered by a change to a Firestore document."""
    import sys
    print("🔔 FUNCTION TRIGGERED - STARTING EXECUTION", file=sys.stderr)
    
    try:
        # Handle both binary and JSON formats
        if isinstance(cloud_event.data, bytes):
            print("📦 Received binary data", file=sys.stderr)
            # For binary data, try various decoding approaches
            try:
                # First try decoding as UTF-8 JSON
                decoded_data = json.loads(cloud_event.data.decode('utf-8'))
                print("✅ Successfully decoded binary data as JSON", file=sys.stderr)
                cloud_event.data = decoded_data
            except:
                # If that fails, try decoding as base64
                try:
                    import base64
                    decoded_bytes = base64.b64decode(cloud_event.data)
                    decoded_data = json.loads(decoded_bytes.decode('utf-8'))
                    print("✅ Successfully decoded binary data as base64 JSON", file=sys.stderr)
                    cloud_event.data = decoded_data
                except:
                    print(f"❌ Could not decode binary data", file=sys.stderr)
                    print(f"📦 First few bytes: {cloud_event.data[:30].hex()}", file=sys.stderr)
                    return
    
        # Now we should have JSON data
        print("📦 Event data:", json.dumps(cloud_event.data, indent=2), file=sys.stderr)
        
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
        if "updateMask" in cloud_event.data and "fieldPaths" in cloud_event.data["updateMask"]:
            field_paths = cloud_event.data["updateMask"]["fieldPaths"]
            if "notification_preferences" not in field_paths:
                print("⏭️ Notification preferences not updated", file=sys.stderr)
                # Continue anyway to handle the notification time
                
        # Access top-level next_notification_time field
        next_time = changed_data.get("next_notification_time", {}).get("timestampValue")
        if not next_time:
            print("⚠️ No next_notification_time found in top-level fields", file=sys.stderr)
        
        # Fetch user document from Firestore
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            print(f"❌ User document {user_id} not found", file=sys.stderr)
            return
        
        user_data = user_doc.to_dict()
        print(f"📋 User data retrieved: {user_data.get('name', 'Unknown user')}", file=sys.stderr)
        
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
        
        # Cancel any existing scheduled notifications and schedule a new one
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
            
            print(f"✅ Successfully scheduled next notification for {user_id} at {next_time.isoformat()}", file=sys.stderr)
            
        except Exception as schedule_error:
            print(f"❌ Error scheduling notification: {str(schedule_error)}", file=sys.stderr)
            
            # If Cloud Tasks scheduling fails, try direct FCM notification approach as backup
            try:
                # Prepare notification content
                next_day_data = user_data.get('next_day_notification', {})
                notification_content = {
                    'title': next_day_data.get('title', 'Time for Exercise!'),
                    'body': next_day_data.get('body', 'Time to work on your exercises!')
                }
                print(f"📬 Notification content: {notification_content}", file=sys.stderr)
                
                notification_id = str(uuid.uuid4())

                # Compose message
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=notification_content['title'],
                        body=notification_content['body']
                    ),
                    data={
                        'notification_id': notification_id,
                        'user_id': user_id,
                        'type': 'exercise_reminder'
                    },
                    token=fcm_token,
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            priority='high',
                            channel_id='exercise_reminders'
                        )
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                sound='default',
                                badge=1,
                                content_available=True,
                                mutable_content=True,
                                priority=10,
                                category='EXERCISE_REMINDER'
                            )
                        ),
                        headers={
                            'apns-push-type': 'background',
                            'apns-priority': '5',
                            'apns-topic': 'yanfryy.xyz.MVP'  # Your actual iOS bundle ID
                        }
                    )
                )

                # Save notification in Firestore
                notification_data = {
                    'id': notification_id,
                    'user_id': user_id,
                    'type': 'exercise_reminder',
                    'scheduled_for': firestore.SERVER_TIMESTAMP,
                    'status': 'scheduled',
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'content': notification_content
                }
                db.collection('notifications').document(notification_id).set(notification_data)
                print(f"✅ Notification document created: {notification_id}", file=sys.stderr)

                try:
                    response = messaging.send(message)
                    print(f"✅ Notification sent: {response}", file=sys.stderr)

                    db.collection('notifications').document(notification_id).update({
                        'status': 'sent',
                        'sent_at': firestore.SERVER_TIMESTAMP,
                        'message_id': response
                    })
                    print("✅ Notification status updated to 'sent'", file=sys.stderr)

                except Exception as send_error:
                    print(f"❌ Error sending notification: {str(send_error)}", file=sys.stderr)
                    db.collection('notifications').document(notification_id).update({
                        'status': 'failed',
                        'error': str(send_error)
                    })
            except Exception as direct_notify_error:
                print(f"❌ Error with direct notification: {str(direct_notify_error)}", file=sys.stderr)

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
            'updated_at': firestore.SERVER_TIMESTAMP,
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