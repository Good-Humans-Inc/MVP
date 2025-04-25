import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime, timedelta
import json
import uuid
from google.cloud import secretmanager
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
from openai import OpenAI

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
                        badge=1
                    )
                )
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