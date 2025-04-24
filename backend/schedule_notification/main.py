import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime, timedelta
import json
import uuid
from google.cloud import secretmanager
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds

# Initialize Firebase Admin with default credentials
firebase_admin.initialize_app()
db = firestore.Client(project='pepmvp', database='pep-mvp')

def get_secret(secret_id):
    """Get secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/pepmvp/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

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
        
        # Get user's FCM token
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
        
        # Create notification document
        notification_data = {
            'id': notification_id,
            'user_id': user_id,
            'type': 'exercise_reminder',
            'scheduled_for': scheduled_datetime,
            'status': 'scheduled',
            'created_at': firestore.SERVER_TIMESTAMP,
            'is_one_time': is_one_time
        }
        
        # Add to Firestore
        db.collection('notifications').document(notification_id).set(notification_data)
        
        # Get user's notification preferences and stored message
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict()
        
        # Get notification time from user preferences or use provided time
        notification_time = scheduled_time
        if not is_one_time:
            # For recurring notifications, use user's preferred time
            preferred_time = user_data.get('notification_preferences', {}).get('time', {})
            if preferred_time:
                notification_time = notification_time.replace(
                    hour=preferred_time.get('hour', 9),
                    minute=preferred_time.get('minute', 0)
                )
        
        # Get stored notification message
        next_day_notification = user_data.get('next_day_notification', {})
        
        # Create message
        message = messaging.Message(
            notification=messaging.Notification(
                title=next_day_notification.get('title', "Time for your PT exercises!"),
                body=next_day_notification.get('body', "Don't forget to complete your physical therapy exercises today.")
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
                        badge=1
                    )
                )
            )
        )
        
        # Schedule the message
        response = messaging.send(message)
        
        # Update notification status
        db.collection('notifications').document(notification_id).update({
            'status': 'sent',
            'sent_at': firestore.SERVER_TIMESTAMP,
            'message_id': response
        })
        
        # If this is a one-time notification, schedule the next one using the original time
        if is_one_time:
            # Get the original notification schedule
            original_schedule = user_data.get('notification_schedule', {})
            original_hour = original_schedule.get('hour', 9)  # Default to 9 AM if not set
            original_minute = original_schedule.get('minute', 0)  # Default to 0 if not set
            
            # Calculate the next notification time after this one (day after tomorrow)
            next_notification_time = scheduled_datetime + timedelta(days=1)
            next_notification_time = next_notification_time.replace(
                hour=original_hour,
                minute=original_minute,
                second=0,
                microsecond=0
            )
            
            # Update the user's next notification time to use the original schedule
            user_ref.update({
                'notification_schedule.next_notification': next_notification_time,
                'notification_schedule.temporary_override': firestore.DELETE_FIELD
            })
            
            # Schedule the next notification using the original time
            next_notification_time_str = next_notification_time.isoformat() + 'Z'
            
            # Create a new request for the next notification
            next_notification_request = MockRequest({
                'user_id': user_id,
                'scheduled_time': next_notification_time_str,
                'is_one_time': False  # This will be a regular notification
            })
            
            # Schedule the next notification
            schedule_notification(next_notification_request)
        
        return (json.dumps({
            'status': 'success',
            'notification_id': notification_id,
            'message_id': response
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
                        badge=1
                    )
                )
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