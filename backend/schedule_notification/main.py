import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime, timedelta, timezone
import json
import uuid
from google.cloud import secretmanager
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
from openai import OpenAI
from google.cloud.functions.context import Context

# Initialize Firebase Admin with default credentials
firebase_admin.initialize_app()
db = firestore.Client(project='pepmvp', database='pep-mvp')

def get_secret(secret_id):
    """Get secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/pepmvp/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def generate_notification_content(user_name, exercise_names, user_data):
    """Generate personalized notification content using OpenAI."""
    try:
        client = OpenAI(api_key=get_secret('openai-api-key'))
        
        # Get user's preferences and history
        preferred_tone = user_data.get('notification_preferences', {}).get('tone', 'friendly')
        exercise_history = user_data.get('exercise_history', [])
        streak = len(exercise_history)
        
        # Create prompt for OpenAI
        prompt = f"""Generate a motivational exercise reminder notification for a physical therapy user with the following details:

User Name: {user_name}
Exercises: {', '.join(exercise_names)}
Current Streak: {streak} days
Preferred Tone: {preferred_tone}

The notification should have:
1. A catchy title (max 44 characters)
2. A motivational message (max 150 characters)
3. Be {preferred_tone} in tone
4. Mention specific exercises if provided
5. Include streak information if significant (>3 days)

Format the response as JSON:
{{
    "title": "string",
    "body": "string"
}}"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a motivational physical therapy assistant crafting engaging notifications."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        # Parse the response
        content = json.loads(response.choices[0].message.content)
        return content
        
    except Exception as e:
        print(f"Error generating notification content: {str(e)}")
        # Return default content if OpenAI generation fails
        return {
            "title": "Time for your PT exercises!",
            "body": f"Hi {user_name}! Ready to continue your progress? Let's work on your exercises today!"
        }

@functions_framework.http
def schedule_notification(request):
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        # Get request data
        request_json = request.get_json()
        user_id = request_json.get('user_id')
        scheduled_time = request_json.get('scheduled_time')
        is_one_time = request_json.get('is_one_time', False)
        
        if not user_id:
            return (json.dumps({'error': 'Missing user_id'}), 400, headers)
        
        # Get user's data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        user_data = user_doc.to_dict()
        fcm_token = user_data.get('fcm_token')
        
        if not fcm_token:
            return (json.dumps({'error': 'User has no FCM token'}), 400, headers)
        
        # Parse scheduled time
        try:
            scheduled_datetime = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return (json.dumps({'error': 'Invalid scheduled_time format'}), 400, headers)
        
        # Create notification ID
        notification_id = str(uuid.uuid4())
        
        # Get user's exercises
        exercises_ref = db.collection('user_exercises').where('user_id', '==', user_id).limit(1).get()
        exercise_names = []
        for exercise_doc in exercises_ref:
            exercise_data = exercise_doc.to_dict()
            exercise_names.append(exercise_data.get('name', 'your exercise'))
        
        # Generate personalized notification content
        notification_content = generate_notification_content(
            user_name=user_data.get('name', 'there'),
            exercise_names=exercise_names,
            user_data=user_data
        )
        
        # Create notification document
        notification_data = {
            'id': notification_id,
            'user_id': user_id,
            'type': 'exercise_reminder',
            'scheduled_for': scheduled_datetime,
            'status': 'scheduled',
            'created_at': firestore.SERVER_TIMESTAMP,
            'is_one_time': is_one_time,
            'content': notification_content
        }
        
        # Add to Firestore
        db.collection('notifications').document(notification_id).set(notification_data)
        
        # Create message
        message = messaging.Message(
            notification=messaging.Notification(
                title=notification_content['title'],
                body=notification_content['body']
            ),
            data={
                'notification_id': notification_id,
                'user_id': user_id,
                'type': 'exercise_reminder',
                'is_one_time': str(is_one_time).lower()
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
                        content_available=True,  # Enable background notification processing
                        mutable_content=True,    # Allow notification modification before display
                        category='EXERCISE_REMINDER'  # For custom notification actions
                    )
                ),
                headers={
                    'apns-push-type': 'background',
                    'apns-priority': '5',
                    'apns-topic': 'com.pepmvp.app'  # Replace with your app bundle ID
                }
            )
        )
        
        # Send the message
        response = messaging.send(message)
        
        # Update notification status
        db.collection('notifications').document(notification_id).update({
            'status': 'sent',
            'sent_at': firestore.SERVER_TIMESTAMP,
            'message_id': response
        })
        
        # If this is a one-time notification, update the next regular notification time
        if is_one_time:
            # Get the regular notification schedule
            notification_prefs = user_data.get('notification_preferences', {})
            regular_hour = notification_prefs.get('hour', 9)  # Default to 9 AM
            regular_minute = notification_prefs.get('minute', 0)
            
            # Calculate next regular notification time (next day)
            next_notification = scheduled_datetime + timedelta(days=1)
            next_notification = next_notification.replace(
                hour=regular_hour,
                minute=regular_minute,
                second=0,
                microsecond=0
            )
            
            # Update the user's next notification time
            user_ref.update({
                'next_notification_time': next_notification
            })
        
        return (json.dumps({
            'status': 'success',
            'notification_id': notification_id,
            'message_id': response,
            'scheduled_for': scheduled_datetime.isoformat(),
            'content': notification_content
        }), 200, headers)
            
    except Exception as e:
        print(f"Error scheduling notification: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

# Helper class for creating mock requests
class MockRequest:
    def __init__(self, json_data):
        self.json_data = json_data
    
    def get_json(self):
        return self.json_data

@functions_framework.http
def update_fcm_token(request):
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        # Get request data
        request_json = request.get_json()
        user_id = request_json.get('user_id')
        fcm_token = request_json.get('fcm_token')
        
        if not user_id or not fcm_token:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Update user's FCM token
        user_ref = db.collection('users').document(user_id)
        user_ref.update({
            'fcm_token': fcm_token,
            'last_token_update': firestore.SERVER_TIMESTAMP
        })
        
        return (json.dumps({'status': 'success'}), 200, headers)
            
    except Exception as e:
        print(f"Error updating FCM token: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

@functions_framework.http
def send_exercise_notification(request):
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        # Get request data
        request_json = request.get_json()
        user_id = request_json.get('user_id')
        exercise_id = request_json.get('exercise_id')
        
        if not user_id or not exercise_id:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get user's FCM token
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        user_data = user_doc.to_dict()
        fcm_token = user_data.get('fcm_token')
        
        if not fcm_token:
            return (json.dumps({'error': 'User has no FCM token'}), 400, headers)
        
        # Get exercise details
        exercise_ref = db.collection('exercises').document(exercise_id)
        exercise_doc = exercise_ref.get()
        
        if not exercise_doc.exists:
            return (json.dumps({'error': 'Exercise not found'}), 404, headers)
        
        exercise_data = exercise_doc.to_dict()
        
        # Create notification ID
        notification_id = str(uuid.uuid4())
        
        # Create notification content
        title = f"Time for your {exercise_data.get('name', 'PT')} exercise!"
        body = f"Don't forget to complete your {exercise_data.get('name', 'physical therapy')} exercise today."
        
        # Create message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data={
                'notification_id': notification_id,
                'user_id': user_id,
                'type': 'exercise_reminder',
                'exercise_id': exercise_id
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
                        category='EXERCISE_REMINDER'
                    )
                ),
                headers={
                    'apns-push-type': 'background',
                    'apns-priority': '5',
                    'apns-topic': 'com.pepmvp.app'
                }
            )
        )
        
        # Send the message
        response = messaging.send(message)
        
        # Create notification document
        notification_data = {
            'id': notification_id,
            'user_id': user_id,
            'type': 'exercise_reminder',
            'scheduled_for': firestore.SERVER_TIMESTAMP,
            'sent_at': firestore.SERVER_TIMESTAMP,
            'status': 'sent',
            'created_at': firestore.SERVER_TIMESTAMP,
            'exercise_id': exercise_id,
            'message_id': response
        }
        
        # Add to Firestore
        db.collection('notifications').document(notification_id).set(notification_data)
        
        return (json.dumps({
            'status': 'success',
            'notification_id': notification_id,
            'message_id': response
        }), 200, headers)
            
    except Exception as e:
        print(f"Error sending exercise notification: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

# Helper function to serialize Firestore data for JSON
def serialize_firestore_data(data):
    """Helper function to serialize Firestore data for JSON."""
    if isinstance(data, dict):
        return {k: serialize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_firestore_data(item) for item in data]
    elif isinstance(data, DatetimeWithNanoseconds):
        return data.isoformat()
    elif hasattr(data, 'datetime'):  # Handle Firestore Timestamp
        return data.datetime.isoformat()
    else:
        return data 

@functions_framework.http
def check_notification_status(request):
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        # Get request data
        request_json = request.get_json()
        notification_id = request_json.get('notification_id')
        
        if not notification_id:
            return (json.dumps({'error': 'Missing notification_id'}), 400, headers)
        
        # Get notification document
        notification_ref = db.collection('notifications').document(notification_id)
        notification_doc = notification_ref.get()
        
        if not notification_doc.exists:
            return (json.dumps({'error': 'Notification not found'}), 404, headers)
        
        notification_data = notification_doc.to_dict()
        user_id = notification_data.get('user_id')
        
        # Get user's FCM token for verification
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict()
        
        # Prepare debug info
        debug_info = {
            'notification': serialize_firestore_data(notification_data),
            'fcm_token_exists': bool(user_data.get('fcm_token')),
            'fcm_token_last_update': serialize_firestore_data(user_data.get('last_token_update')),
            'notification_preferences': user_data.get('notification_preferences', {}),
            'app_notification_status': user_data.get('notification_status', 'unknown')
        }
        
        return (json.dumps({
            'status': 'success',
            'debug_info': debug_info
        }), 200, headers)
            
    except Exception as e:
        print(f"Error checking notification status: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

@functions_framework.cloud_event
def monitor_notification_changes(cloud_event):
    """Triggered by a Firestore document change on 'users/{userId}'."""
    import sys
    from datetime import datetime, timezone, timedelta
    import json
    import re

    print("🔔 FUNCTION TRIGGERED - STARTING EXECUTION", file=sys.stderr)
    
    try:
        # Get the raw data as bytes
        raw_data = cloud_event.data
        
        if not raw_data:
            print("❌ Empty event data received", file=sys.stderr)
            return
            
        # Convert to string for debugging
        data_str = str(raw_data) if raw_data else ""
        print(f"📦 Raw event data: {data_str[:200]}...", file=sys.stderr)
        
        # Extract user ID using regex - look for two different patterns from the logs
        # Pattern 1: users/{userId} in the main path
        match = re.search(r'users/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', data_str)
        if not match:
            # Pattern 2: user_id value in JSON
            match = re.search(r'user_id\\x12\\x[0-9a-f]+\\x01([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', data_str)
            
        if not match:
            print("❌ Could not find user ID in event data - trying alternate method", file=sys.stderr)
            # Try extracting from document path
            if hasattr(cloud_event, 'subject'):
                subject = cloud_event.subject
                print(f"📄 Event subject: {subject}", file=sys.stderr)
                # Extract from subject like "projects/pepmvp/databases/pep-mvp/documents/users/9b11420d-be73-49fd-af1d-bff1ed4f66a0"
                match = re.search(r'documents/users/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', subject)
            
        if not match:
            print("❌ Failed to extract user ID, using default test user", file=sys.stderr)
            # Use a default test user ID for debugging
            user_id = "9b11420d-be73-49fd-af1d-bff1ed4f66a0"  # Default test user
        else:
            user_id = match.group(1)
            
        print(f"👤 Found User ID: {user_id}", file=sys.stderr)
        
        # Fetch the full user document from Firestore
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            print(f"❌ User document {user_id} not found", file=sys.stderr)
            return
        
        user_data = user_doc.to_dict()
        username = user_data.get('name', 'Unknown user')
        print(f"📋 User data retrieved: {username}", file=sys.stderr)
        
        notification_prefs = user_data.get('notification_preferences', {})
        print(f"🔍 User notification preferences: {notification_prefs}", file=sys.stderr)
        
        # Get the next notification time from user data
        next_time = user_data.get('next_notification_time')
        if not next_time:
            print("⚠️ No next_notification_time found in user data, checking other fields", file=sys.stderr)
            # Check for notification_preferences as fallback
            if notification_prefs.get('is_enabled'):
                hour = notification_prefs.get('hour')
                minute = notification_prefs.get('minute')
                if hour is not None and minute is not None:
                    print(f"⚠️ Using notification preferences time: {hour}:{minute}", file=sys.stderr)
                    # Create next notification time
                    now = datetime.now(timezone.utc)
                    next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if next_time < now:
                        next_time = next_time + timedelta(days=1)
                    # Update user's next_notification_time
                    user_ref.update({
                        'next_notification_time': next_time
                    })
                    print(f"⚠️ Updated user's next_notification_time to {next_time}", file=sys.stderr)
                else:
                    print("❌ Cannot create next_notification_time, missing hour/minute", file=sys.stderr)
                    return
            else:
                print("❌ Notifications not enabled for user", file=sys.stderr)
                return
        
        # Convert to datetime if it's a Firestore timestamp
        if hasattr(next_time, 'timestamp'):
            next_time_dt = datetime.fromtimestamp(next_time.timestamp(), tz=timezone.utc)
        else:
            try:
                next_time_dt = datetime.fromisoformat(str(next_time).replace('Z', '+00:00'))
            except (ValueError, TypeError) as e:
                print(f"❌ Error parsing next_notification_time: {str(e)} - Value: {next_time}", file=sys.stderr)
                return
        
        print(f"⏰ Next notification time: {next_time_dt.isoformat()}", file=sys.stderr)
        
        # Get FCM token
        fcm_token = user_data.get('fcm_token')
        if not fcm_token:
            print(f"❌ No FCM token found for user {user_id}", file=sys.stderr)
            return
        
        # Verify if the notification time is now or in the past - NO TIME WINDOW RESTRICTION
        current_time = datetime.now(timezone.utc)
        time_diff = (next_time_dt - current_time).total_seconds()
        
        print(f"⏱️ Time difference: {time_diff} seconds (current: {current_time.isoformat()}, next: {next_time_dt.isoformat()})", file=sys.stderr)
        
        # Only skip if notification time is more than 30 minutes in the future
        if time_diff > 1800:  # 30 minutes in seconds
            print(f"⏭️ Skipping - Notification time {next_time_dt} is more than 30 minutes in the future", file=sys.stderr)
            return
            
        print(f"✅ Processing notification for time {next_time_dt}", file=sys.stderr)
        
        # Check for duplicate notifications in the last 5 minutes
        five_mins_ago = current_time - timedelta(minutes=5)
        recent_notifications = db.collection('notifications') \
            .where('user_id', '==', user_id) \
            .where('created_at', '>', five_mins_ago) \
            .where('type', '==', 'exercise_reminder') \
            .limit(1) \
            .get()
        
        if len(list(recent_notifications)):
            print("⏭️ Skipping - Recent notification already sent", file=sys.stderr)
            return
        
        print(f"📱 Found FCM token: {fcm_token[:10]}...", file=sys.stderr)
        
        # Compose the notification
        next_day_data = user_data.get('next_day_notification', {})
        if not next_day_data:
            print("⚠️ No next_day_notification data found, using default content", file=sys.stderr)
            notification_content = {
                'title': f"Time for Exercise, {username}!",
                'body': "It's time for your daily exercise routine. Let's keep that streak going!"
            }
        else:
            notification_content = {
                'title': next_day_data.get('title', f"Time for Exercise, {username}!"),
                'body': next_day_data.get('body', "It's time for your daily exercise routine!")
            }
            
        print(f"📬 Notification content: {notification_content}", file=sys.stderr)
        
        notification_id = str(uuid.uuid4())
        print(f"🆔 Created notification ID: {notification_id}", file=sys.stderr)
        
        # App bundle ID for APNs
        bundle_id = user_data.get('app_bundle_id', 'com.pepmvp.app')
        device_type = user_data.get('device_type', 'unknown')
        print(f"📲 Device type: {device_type}, Bundle ID: {bundle_id}", file=sys.stderr)
        
        # Save notification record first
        notification_data = {
            'id': notification_id,
            'user_id': user_id,
            'type': 'exercise_reminder',
            'scheduled_for': next_time_dt,
            'status': 'scheduled',
            'created_at': firestore.SERVER_TIMESTAMP,
            'content': notification_content,
            'is_one_time': True  # Adding is_one_time flag
        }
        db.collection('notifications').document(notification_id).set(notification_data)
        print(f"✅ Notification document created: {notification_id}", file=sys.stderr)
        
        # APNS configuration based on device type
        if device_type and device_type.lower() == 'ios':
            # Enhanced iOS configuration with alert
            apns_config = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=notification_content['title'],
                            body=notification_content['body']
                        ),
                        sound='default',
                        badge=1,
                        content_available=True,
                        mutable_content=True,
                        category='EXERCISE_REMINDER'
                    )
                ),
                headers={
                    'apns-push-type': 'alert',
                    'apns-priority': '10',  # High priority for immediate delivery
                    'apns-topic': bundle_id
                }
            )
        else:
            # Standard configuration for other devices
            apns_config = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1,
                        content_available=True,
                        mutable_content=True,
                        category='EXERCISE_REMINDER'
                    )
                ),
                headers={
                    'apns-push-type': 'background',
                    'apns-priority': '5',
                    'apns-topic': bundle_id
                }
            )
        
        # Compose FCM message
        message = messaging.Message(
            notification=messaging.Notification(
                title=notification_content['title'],
                body=notification_content['body']
            ),
            data={
                'notification_id': notification_id,
                'user_id': user_id,
                'type': 'exercise_reminder',
                'scheduled_time': next_time_dt.isoformat(),
                'is_one_time': 'true'  # Include is_one_time in data payload
            },
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    priority='high',
                    channel_id='exercise_reminders'
                )
            ),
            apns=apns_config
        )
        
        # Try sending the notification
        try:
            response = messaging.send(message)
            print(f"✅ Notification sent successfully: {response}", file=sys.stderr)
            
            db.collection('notifications').document(notification_id).update({
                'status': 'sent',
                'sent_at': firestore.SERVER_TIMESTAMP,
                'message_id': response
            })
            print("✅ Notification status updated to 'sent'", file=sys.stderr)
            
            # Schedule next notification using preferences
            if notification_prefs.get('is_enabled') and notification_prefs.get('frequency') == 'daily':
                hour = notification_prefs.get('hour')
                minute = notification_prefs.get('minute')
                if hour is not None and minute is not None:
                    # Calculate next day at the same hour/minute
                    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
                    next_notification = tomorrow.replace(
                        hour=hour, 
                        minute=minute, 
                        second=0, 
                        microsecond=0
                    )
                    
                    user_ref.update({
                        'next_notification_time': next_notification
                    })
                    print(f"⏰ Scheduled next notification for: {next_notification.isoformat()}", file=sys.stderr)
            
        except messaging.ApiCallError as fcm_error:
            error_msg = str(fcm_error)
            print(f"❌ FCM API Error: {error_msg}", file=sys.stderr)
            
            if 'registration-token-not-registered' in error_msg.lower():
                print("🔄 FCM token expired, updating user doc", file=sys.stderr)
                user_ref.update({
                    'fcm_token': firestore.DELETE_FIELD,
                    'notification_status': 'token_expired'
                })
            
            db.collection('notifications').document(notification_id).update({
                'status': 'failed',
                'error': error_msg
            })
        except Exception as send_error:
            print(f"❌ Error sending notification: {str(send_error)}", file=sys.stderr)
            db.collection('notifications').document(notification_id).update({
                'status': 'failed',
                'error': str(send_error)
            })
    
    except Exception as e:
        print(f"❌ GENERAL ERROR: {str(e)}", file=sys.stderr)
        import traceback
        print("📋 Stack trace:", traceback.format_exc(), file=sys.stderr)

@functions_framework.http
def check_notifications(request):
    """Check scheduled notifications for a user."""
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        request_json = request.get_json()
        user_id = request_json.get('user_id')
        
        if not user_id:
            return (json.dumps({'error': 'Missing user_id'}), 400, headers)
        
        # Get user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        user_data = user_doc.to_dict()
        
        # Get notification preferences and next notification time
        notification_prefs = user_data.get('notification_preferences', {})
        next_notification_time = user_data.get('next_notification_time')
        next_day_notification = user_data.get('next_day_notification', {})
        
        # Get recent and upcoming notifications
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        
        notifications = db.collection('notifications') \
            .where('user_id', '==', user_id) \
            .where('scheduled_for', '>', yesterday) \
            .order_by('scheduled_for', direction=firestore.Query.DESCENDING) \
            .limit(10) \
            .stream()
        
        notifications_list = []
        for notif in notifications:
            notif_data = notif.to_dict()
            notifications_list.append(serialize_firestore_data(notif_data))
        
        return (json.dumps({
            'status': 'success',
            'notification_preferences': notification_prefs,
            'next_notification_time': serialize_firestore_data(next_notification_time),
            'next_day_notification': next_day_notification,
            'recent_notifications': notifications_list,
            'current_time_utc': now.isoformat()
        }), 200, headers)
            
    except Exception as e:
        print(f"Error checking notifications: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)