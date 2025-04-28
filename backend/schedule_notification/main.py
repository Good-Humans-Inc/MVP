# schedule_notification/main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone
import json
import uuid
from google.cloud import tasks_v2
import google.auth

# Initialize Firebase Admin if not already initialized
try:
    app = firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()

db = firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.http
def schedule_notification(request):
    """
    Schedule a notification using Google Cloud Tasks.
    
    Expected request format:
    {
        "user_id": "string",
        "scheduled_time": "ISO datetime string",
        "is_one_time": boolean,
        "custom_title": "string", (optional)
        "custom_body": "string" (optional)
    }
    """
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
        scheduled_time_str = request_json.get('scheduled_time')
        is_one_time = request_json.get('is_one_time', False)
        custom_title = request_json.get('custom_title', None)
        custom_body = request_json.get('custom_body', None)
        
        # Validate required parameters
        if not user_id or not scheduled_time_str:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get user data to verify existence and get FCM token
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        user_data = user_doc.to_dict()
        
        # Check for FCM token
        fcm_token = user_data.get('fcm_token')
        if not fcm_token:
            return (json.dumps({'error': 'No FCM token found for user'}), 400, headers)
        
        # Create notification ID for tracking
        notification_id = str(uuid.uuid4())
        
        # Parse scheduled time
        try:
            scheduled_time = datetime.fromisoformat(scheduled_time_str.replace('Z', '+00:00'))
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return (json.dumps({'error': 'Invalid scheduled_time format. Use ISO 8601 format.'}), 400, headers)
        
        # Determine notification content (prioritize custom, then next_day_notification, then default)
        username = user_data.get('name', 'User')
        
        if custom_title and custom_body:
            notification_title = custom_title
            notification_body = custom_body
        else:
            # We'll use next_day_notification if available, but this will be checked again
            # at send time to get the most up-to-date personalized content
            notification_title = f"Time for Exercise, {username}!"
            notification_body = "It's time for your daily exercise routine. Let's keep that streak going!"
        
        # Store notification in Firestore
        notification_data = {
            'id': notification_id,
            'user_id': user_id,
            'type': 'exercise_reminder',
            'scheduled_for': scheduled_time,
            'status': 'scheduled',
            'created_at': firestore.SERVER_TIMESTAMP,
            'is_one_time': is_one_time,
            'content': {
                'title': notification_title,
                'body': notification_body
            }
        }
        
        db.collection('notifications').document(notification_id).set(notification_data)
        
        # Create Cloud Task to send the notification at the scheduled time
        credentials, project_id = google.auth.default()
        task_client = tasks_v2.CloudTasksClient()
        
        # Set up Cloud Tasks location and queue
        parent = task_client.queue_path(
            'pepmvp',  # Your project ID
            'us-central1',  # Choose your region
            'notification-queue'  # Your queue name - create this in GCP Console
        )
        
        # Calculate seconds from epoch for the scheduled time
        scheduled_seconds = int(scheduled_time.timestamp())
        
        # Create payload for the Cloud Task
        payload = {
            'notification_id': notification_id,
            'user_id': user_id
        }
        
        # URL of the Cloud Function that will send the notification
        url = f"https://us-central1-pepmvp.cloudfunctions.net/send_notification"
        
        # Create the task
        task = {
            'http_request': {
                'http_method': tasks_v2.HttpMethod.POST,
                'url': url,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps(payload).encode()
            },
            'schedule_time': {
                'seconds': scheduled_seconds
            },
            'name': f"projects/pepmvp/locations/us-central1/queues/notification-queue/tasks/{notification_id}"
        }
        
        # Create the Cloud Task
        response = task_client.create_task(request={'parent': parent, 'task': task})
        
        # Update notification with task information
        db.collection('notifications').document(notification_id).update({
            'task_name': response.name,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        # If this is a recurring notification, update the user's next_notification_time
        if not is_one_time:
            user_ref.update({
                'next_notification_time': scheduled_time
            })
        
        return (json.dumps({
            'status': 'success',
            'message': 'Notification scheduled successfully',
            'notification_id': notification_id,
            'scheduled_for': serialize_firestore_data(scheduled_time),
            'task_name': response.name
        }), 200, headers)
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error scheduling notification: {str(e)}\n{error_details}")
        return (json.dumps({'error': str(e)}), 500, headers)

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