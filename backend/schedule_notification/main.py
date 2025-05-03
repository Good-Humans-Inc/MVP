import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone, timedelta
import json
import uuid
from google.cloud import tasks_v2
import google.auth
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        "force_today": boolean (optional)
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
        force_today = request_json.get('force_today', False)
        
        logger.info(f"Received schedule request for user {user_id}: is_one_time={is_one_time}, force_today={force_today}")
        
        # Validate required parameters
        if not user_id or not scheduled_time_str:
            logger.error(f"Missing required parameters: user_id={user_id}, scheduled_time={scheduled_time_str}")
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get user data to verify existence and get FCM token
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.error(f"User not found: {user_id}")
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        user_data = user_doc.to_dict()
        
        # Check for FCM token
        fcm_token = user_data.get('fcm_token')
        if not fcm_token:
            logger.error(f"No FCM token found for user {user_id}")
            return (json.dumps({'error': 'No FCM token found for user'}), 400, headers)
        
        # Get timezone offset from user data
        user_timezone_offset = extract_timezone_offset(user_data)
        logger.info(f"User {user_id} timezone offset: UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}")
            
        # Create notification ID for tracking
        notification_id = str(uuid.uuid4())
        
        # Parse scheduled time - all incoming times should be in UTC
        try:
            scheduled_time = parse_datetime_to_utc(scheduled_time_str)
            logger.info(f"Parsed scheduled time (UTC): {scheduled_time.isoformat()}")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid scheduled_time format: {scheduled_time_str}. Error: {str(e)}")
            return (json.dumps({'error': 'Invalid scheduled_time format. Use ISO 8601 format.'}), 400, headers)
        
        # Determine notification content
        username = user_data.get('name', 'User')
        
        if custom_title and custom_body:
            notification_title = custom_title
            notification_body = custom_body
            logger.info(f"Using custom notification content for user {user_id}")
        else:
            # Default notification content
            notification_title = f"Time for Exercise, {username}!"
            notification_body = "It's time for your daily exercise routine. Let's keep that streak going!"
            logger.info(f"Using default notification content for user {user_id}")
        
        # Store notification in Firestore
        notification_data = {
            'id': notification_id,
            'user_id': user_id,
            'type': 'exercise_reminder',
            'scheduled_for': scheduled_time,
            'scheduled_time_utc': scheduled_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            'status': 'scheduled',
            'created_at': firestore.SERVER_TIMESTAMP,
            'is_one_time': is_one_time,
            'content': {
                'title': notification_title,
                'body': notification_body
            },
            'user_timezone_offset': user_timezone_offset,
            'force_today': force_today
        }
        
        db.collection('notifications').document(notification_id).set(notification_data)
        logger.info(f"Created notification document {notification_id} for user {user_id}")
        
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
        
        logger.info(f"Creating Cloud Task for notification {notification_id} scheduled at {scheduled_time.isoformat()}")
        
        # Create the Cloud Task
        response = task_client.create_task(request={'parent': parent, 'task': task})
        logger.info(f"Created Cloud Task: {response.name}")
        
        # Update notification with task information
        db.collection('notifications').document(notification_id).update({
            'task_name': response.name,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        # If this is a recurring notification, update the user's next_notification_time
        if not is_one_time:
            logger.info(f"Updating user {user_id} with next_notification_time: {scheduled_time.isoformat()}")
            user_ref.update({
                'next_notification_time': scheduled_time,
                'next_notification_time_utc': scheduled_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                'next_notification_utc_hour': scheduled_time.hour,
                'next_notification_utc_minute': scheduled_time.minute
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
        logger.error(f"Error scheduling notification: {str(e)}\n{error_details}")
        return (json.dumps({'error': str(e)}), 500, headers)

def parse_datetime_to_utc(datetime_str):
    """Parse a datetime string to a UTC datetime object."""
    # If string ends with Z, it's already in UTC
    if datetime_str.endswith('Z'):
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    # If string has a timezone, respect it
    elif '+' in datetime_str or '-' in datetime_str:
        dt = datetime.fromisoformat(datetime_str)
    # If no timezone specified, assume UTC
    else:
        dt = datetime.fromisoformat(datetime_str).replace(tzinfo=timezone.utc)
    
    # Convert to UTC if it's not already
    if dt.tzinfo != timezone.utc:
        dt = dt.astimezone(timezone.utc)
    
    return dt

def extract_timezone_offset(user_data):
    """Extract timezone offset from user data consistently."""
    # First, check for the explicit timezone field (which appears in your user document)
    print("🕒 extract_timezone_offset: Checking for timezone field")
    print(f"User data: {user_data}")
    if 'timezone' in user_data:
        try:
            timezone_value = user_data.get('timezone')
            if isinstance(timezone_value, str):
                # Remove quotes if present
                timezone_value = timezone_value.strip('"\'')
            timezone_offset = float(timezone_value)
            logger.info(f"Extracted timezone offset {timezone_offset} from timezone field")
            return timezone_offset
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert timezone value '{user_data.get('timezone')}' to float: {str(e)}")
    
    # Next, try to get from notification_preferences
    notification_prefs = user_data.get('notification_preferences', {})
    timezone_offset = notification_prefs.get('timezone_offset')
    if timezone_offset is not None:
        return timezone_offset
    
    # If not there, try notification_timezone_offset
    timezone_offset = user_data.get('notification_timezone_offset')
    if timezone_offset is not None:
        return timezone_offset
    
    # If still not found, try to extract from timestamps
    if timezone_offset is None:
        timezone_indicators = ['last_updated', 'last_token_update', 'updated_at', 'next_notification_time']
        for field in timezone_indicators:
            if field in user_data and user_data[field]:
                timestamp_value = user_data[field]
                # Check if the timestamp has timezone information
                if hasattr(timestamp_value, 'tzinfo') and timestamp_value.tzinfo:
                    timezone_offset = timestamp_value.utcoffset().total_seconds() / 3600
                    logger.info(f"Extracted timezone offset {timezone_offset} from {field}")
                    break
    
    # Default to UTC if still not found
    if timezone_offset is None:
        logger.warning("Could not determine user timezone, defaulting to UTC")
        timezone_offset = 0
        
    return timezone_offset

# Helper function to serialize Firestore data for JSON
def serialize_firestore_data(data):
    """Helper function to serialize Firestore data for JSON."""
    if isinstance(data, dict):
        return {k: serialize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_firestore_data(item) for item in data]
    elif hasattr(data, 'datetime'):  # Handle Firestore Timestamp
        return data.datetime.isoformat()
    elif hasattr(data, '__class__') and data.__class__.__name__ == 'DatetimeWithNanoseconds':
        # Explicitly handle DatetimeWithNanoseconds
        return data.isoformat()
    elif isinstance(data, datetime):  # Handle Python datetime objects
        return data.isoformat()
    else:
        return data