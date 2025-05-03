# send_notification/main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from google.cloud import secretmanager
import json
from datetime import datetime, timezone, timedelta
import requests
import logging
import traceback
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_firebase_credentials():
    from google.cloud import secretmanager
    import json

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/pepmvp/secrets/firebase-admin-sdk/versions/latest"
    response = client.access_secret_version(name=name)
    return json.loads(response.payload.data.decode("UTF-8"))

# Initialize Firebase Admin
try:
    app = firebase_admin.get_app()
    logging.info(f"✅ Firebase already initialized: {app.name}")
except ValueError:
    cred_dict = get_firebase_credentials()
    cred = credentials.Certificate(cred_dict)
    app = firebase_admin.initialize_app(cred)
    logging.info("✅ Firebase initialized with service account from Secret Manager")


# Debug Firebase credentials and initialization
logger.info("=== FIREBASE INITIALIZATION ===")
logger.info(f"Python version: {sys.version}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Environment variables: {dict(os.environ)}")

# Print service account info if available
service_account_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
if service_account_path:
    logger.info(f"Using service account from: {service_account_path}")
    try:
        with open(service_account_path, 'r') as f:
            service_account_content = f.read()
            # Sanitize the output to hide sensitive info
            logger.info(f"Service account JSON exists and is readable (length: {len(service_account_content)} chars)")
    except Exception as e:
        logger.error(f"Error reading service account file: {str(e)}")
else:
    logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")

# Initialize Firebase Admin if not already initialized
try:
    app = firebase_admin.get_app()
    logger.info(f"Firebase app already initialized: {app.name}")
    logger.info(f"Firebase project ID: {app.project_id}")
    logger.info(f"Firebase options: {app._options}")
except ValueError:
    try:
        # Try with default credentials
        logger.info("Initializing Firebase with default credentials")
        firebase_admin.initialize_app()
        app = firebase_admin.get_app()
        logger.info(f"Firebase initialization succeeded with app name: {app.name}")
        logger.info(f"Firebase project ID: {app.project_id}")
    except Exception as e:
        logger.error(f"Firebase initialization error: {str(e)}")
        logger.error(traceback.format_exc())

db = firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.http
def send_notification(request):
    """
    Send a Firebase Cloud Messaging (FCM) notification to a user.
    This function is triggered by Cloud Tasks at the scheduled time.
    
    Expected request format:
    {
        "notification_id": "string",
        "user_id": "string"
    }
    """
    logger.info("=== SEND_NOTIFICATION FUNCTION STARTED ===")
    # Log the entire raw request for debugging
    request_method = request.method
    request_headers = dict(request.headers)
    request_url = request.url
    request_args = dict(request.args)
    
    # Sanitize headers to remove sensitive information
    if 'Authorization' in request_headers:
        request_headers['Authorization'] = f"{request_headers['Authorization'][:15]}...REDACTED..."
    
    logger.info(f"Request details - Method: {request_method}, URL: {request_url}")
    logger.info(f"Request headers: {request_headers}")
    logger.info(f"Request args: {request_args}")
    
    # Enable CORS
    if request.method == 'OPTIONS':
        logger.info("Handling OPTIONS request (CORS)")
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
        logger.info(f"Request body: {json.dumps(request_json)}")
        
        notification_id = request_json.get('notification_id')
        user_id = request_json.get('user_id')
        
        logger.info(f"Processing notification: {notification_id} for user: {user_id}")
        
        # Validate required parameters
        if not notification_id or not user_id:
            logger.error("Missing required parameters")
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get notification data
        logger.info(f"Fetching notification data from Firestore: {notification_id}")
        notification_ref = db.collection('notifications').document(notification_id)
        notification_doc = notification_ref.get()
        
        if not notification_doc.exists:
            logger.error(f"Notification {notification_id} not found")
            return (json.dumps({'error': 'Notification not found'}), 404, headers)
        
        notification_data = notification_doc.to_dict()
        logger.info(f"Notification data: {json.dumps(serialize_firestore_data(notification_data))}")
        
        # Check if notification was already sent or cancelled
        status = notification_data.get('status')
        if status == 'sent':
            logger.info(f"Notification {notification_id} was already sent")
            return (json.dumps({
                'status': 'warning',
                'message': 'Notification was already sent'
            }), 200, headers)
        elif status == 'cancelled':
            logger.info(f"Notification {notification_id} was cancelled")
            return (json.dumps({
                'status': 'warning',
                'message': 'Notification was cancelled'
            }), 200, headers)
        
        # Get user data
        logger.info(f"Fetching user data from Firestore: {user_id}")
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.error(f"User {user_id} not found")
            notification_ref.update({
                'status': 'failed',
                'error': 'User not found',
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        user_data = user_doc.to_dict()
        # Log user data but sanitize sensitive information
        sanitized_user_data = user_data.copy()
        if 'fcm_token' in sanitized_user_data:
            sanitized_user_data['fcm_token'] = f"{sanitized_user_data['fcm_token'][:10]}...REDACTED..."
        logger.info(f"User data: {json.dumps(serialize_firestore_data(sanitized_user_data))}")
        
        # Check for FCM token
        fcm_token = user_data.get('fcm_token')
        if not fcm_token:
            logger.error(f"No FCM token found for user {user_id}")
            notification_ref.update({
                'status': 'failed',
                'error': 'No FCM token for user',
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            return (json.dumps({'error': 'No FCM token for user'}), 400, headers)
        
        logger.info(f"FCM token found for user: {fcm_token[:10]}...REDACTED...")
        
        # Get notification content - prioritize next_day_notification content
        username = user_data.get('name', 'User')
        next_day_data = user_data.get('next_day_notification', {})
        stored_content = notification_data.get('content', {})
        
        logger.info(f"Username: {username}")
        logger.info(f"Next day notification data available: {bool(next_day_data)}")
        logger.info(f"Next day data: {json.dumps(serialize_firestore_data(next_day_data))}")
        logger.info(f"Stored notification content: {json.dumps(serialize_firestore_data(stored_content))}")
        
        # Get content from next_day_notification if available
        if next_day_data and 'title' in next_day_data and 'body' in next_day_data:
            notification_title = next_day_data.get('title')
            notification_body = next_day_data.get('body')
            logger.info("Using next_day_notification content")
        else:
            # Fallback to content saved with the notification
            notification_title = stored_content.get('title', f"Time for Exercise, {username}!")
            notification_body = stored_content.get('body', "It's time for your daily exercise routine. Let's keep that streak going!")
            logger.info("Using stored notification content")
        
        logger.info(f"Final notification title: {notification_title}")
        logger.info(f"Final notification body: {notification_body}")
        
        # Get user preferences for iOS configuration
        device_type = user_data.get('device_type', 'unknown')
        bundle_id = 'yanffyy.xyz.MVP'
        
        logger.info(f"Device type: {device_type}")
        logger.info(f"Bundle ID: {bundle_id}")
        
        # APNS configuration for iOS
        if device_type and device_type.lower() == 'ios':
            logger.info(f"Creating iOS-specific APNS config with bundle ID: {bundle_id}")
            apns_config = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=notification_title,
                            body=notification_body
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
                    'apns-priority': '10',  # High priority
                    'apns-topic': bundle_id
                }
            )
            logger.info("iOS APNS config created successfully")
        else:
            logger.info("Creating default APNS config for non-iOS device")
            apns_config = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1,
                        content_available=True
                    )
                )
            )
        
        # Compose FCM message
        logger.info("Composing FCM message")
        message = messaging.Message(
            notification=messaging.Notification(
                title=notification_title,
                body=notification_body
            ),
            token=fcm_token,
            data={
                "notification_id": notification_id,
                "user_id": user_id,
                "type": notification_data.get('type', 'generic')
            },
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    priority='high',
                    channel_id='exercise_reminders'
                )
            ),
            apns=apns_config
        )
        
        # Log the message structure (sanitized)
        message_dict = {
            'notification': {
                'title': notification_title,
                'body': notification_body
            },
            'data': {
                'notification_id': notification_id,
                'user_id': user_id,
                'type': notification_data.get('type', 'exercise_reminder')
            },
            'token': f"{fcm_token[:10]}...REDACTED...",
            'android': {
                'priority': 'high',
                'notification': {
                    'priority': 'high',
                    'channel_id': 'exercise_reminders'
                }
            },
            'apns': {
                'headers': {
                    'apns-push-type': 'alert' if device_type.lower() == 'ios' else 'None',
                    'apns-priority': '10' if device_type.lower() == 'ios' else 'None',
                    'apns-topic': bundle_id if device_type.lower() == 'ios' else 'None'
                }
            }
        }
        logger.info(f"FCM message structure: {json.dumps(message_dict)}")
        
        # Send the notification
        try:
            logger.info("Sending FCM notification...")
            response = messaging.send(message)
            logger.info(f"FCM notification sent successfully, response: {response}")
            
            # Update notification status
            logger.info("Updating notification status to 'sent'")
            notification_ref.update({
                'status': 'sent',
                'sent_at': firestore.SERVER_TIMESTAMP,
                'message_id': response,
                'actual_content': {
                    'title': notification_title,
                    'body': notification_body
                }
            })
            
            # If this is a recurring notification, schedule the next one
            is_one_time = notification_data.get('is_one_time', False)
            logger.info(f"Is one-time notification: {is_one_time}")
            
            if not is_one_time:
                logger.info("Processing recurring notification scheduling")
                # Get notification preferences
                notification_prefs = user_data.get('notification_preferences', {})
                logger.info(f"Notification preferences: {json.dumps(serialize_firestore_data(notification_prefs))}")
                
                if notification_prefs.get('is_enabled', False) and notification_prefs.get('frequency') == 'daily':
                    hour = notification_prefs.get('hour')
                    minute = notification_prefs.get('minute')
                    logger.info(f"Notification time: {hour}:{minute}")
                    
                    if hour is not None and minute is not None:
                        # Get user's timezone offset
                        user_timezone_offset = get_user_timezone_offset(user_data)
                        logger.info(f"User timezone offset: UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}")
                        
                        # Calculate next notification time using the standardized function
                        next_time = calculate_next_notification_time(
                            hour=hour,
                            minute=minute,
                            user_timezone_offset=user_timezone_offset
                        )
                        
                        # Update user's next notification time
                        logger.info(f"Updating user's next notification time to {next_time.isoformat()}")
                        user_ref.update({
                            'next_notification_time': next_time
                        })
                        
                        # Schedule the next notification through a separate HTTP call
                        try:
                            # Prepare the request payload
                            payload = {
                                'user_id': user_id,
                                'scheduled_time': next_time.isoformat(),
                                'is_one_time': False
                            }
                            
                            # URL of this Cloud Function
                            url = f"https://us-central1-pepmvp.cloudfunctions.net/schedule_notification"
                            
                            logger.info(f"Scheduling next notification with payload: {json.dumps(payload)}")
                            
                            # Make the HTTP request
                            logger.info(f"Sending request to {url}")
                            schedule_response = requests.post(url, json=payload)
                            
                            logger.info(f"Schedule request status code: {schedule_response.status_code}")
                            
                            if schedule_response.status_code == 200:
                                response_data = schedule_response.json()
                                logger.info(f"Successfully scheduled next notification: {json.dumps(response_data)}")
                            else:
                                logger.error(f"Failed to schedule next notification: {schedule_response.text}")
                        except Exception as schedule_error:
                            logger.error(f"Error scheduling next notification: {str(schedule_error)}")
                            logger.error(traceback.format_exc())
                    else:
                        logger.warning("Missing hour or minute in notification preferences")
                else:
                    logger.info("Recurring notifications not enabled or not set to daily")
            
            return (json.dumps({
                'status': 'success',
                'message': 'Notification sent successfully',
                'fcm_message_id': response
            }), 200, headers)
            
        except Exception as fcm_error:
            error_msg = str(fcm_error)
            error_type = type(fcm_error).__name__
            
            logger.error(f"FCM error type: {error_type}")
            logger.error(f"FCM error message: {error_msg}")
            logger.error(f"FCM error traceback: {traceback.format_exc()}")
            
            # Try to extract more detailed error information if possible
            if hasattr(fcm_error, 'cause'):
                logger.error(f"FCM error cause: {fcm_error.cause}")
            
            if hasattr(fcm_error, 'detail'):
                logger.error(f"FCM error details: {fcm_error.detail}")
                
            if hasattr(fcm_error, 'code'):
                logger.error(f"FCM error code: {fcm_error.code}")
            
            if hasattr(fcm_error, 'message'):
                logger.error(f"FCM error message (from attribute): {fcm_error.message}")
            
            # Handle invalid token
            if 'registration-token-not-registered' in error_msg.lower():
                logger.info(f"Deleting invalid FCM token for user {user_id}")
                user_ref.update({
                    'fcm_token': firestore.DELETE_FIELD,
                    'notification_status': 'token_expired'
                })
            
            # Update notification record
            logger.info("Updating notification status to 'failed'")
            notification_ref.update({
                'status': 'failed',
                'error': error_msg,
                'error_type': error_type,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            return (json.dumps({
                'status': 'error',
                'message': f'FCM API Error: {error_msg}',
                'error_type': error_type
            }), 500, headers)
            
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Unhandled error in send_notification: {str(e)}")
        logger.error(error_details)
        return (json.dumps({
            'error': str(e),
            'error_type': type(e).__name__,
            'stack_trace': error_details
        }), 500, headers)
    
    

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

# Helper function to determine user timezone
def get_user_timezone_offset(user_data):
    """Extract timezone offset from user data timestamps."""
    # First check if timezone field exists directly
    if 'timezone' in user_data:
        try:
            timezone_value = user_data.get('timezone')
            if isinstance(timezone_value, str):
                timezone_value = timezone_value.strip('"\'')
            timezone_offset = float(timezone_value)
            logger.info(f"Found user timezone offset directly: {timezone_offset}")
            return timezone_offset
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert timezone value '{user_data.get('timezone')}' to float: {str(e)}")
    
    # Check the notification_preferences
    notification_prefs = user_data.get('notification_preferences', {})
    timezone_offset = notification_prefs.get('timezone_offset')
    if timezone_offset is not None:
        logger.info(f"Found timezone offset in notification_preferences: {timezone_offset}")
        return timezone_offset
    
    # If not there, try notification_timezone_offset
    timezone_offset = user_data.get('notification_timezone_offset')
    if timezone_offset is not None:
        logger.info(f"Found timezone offset in notification_timezone_offset: {timezone_offset}")
        return timezone_offset
    
    # Try to extract from timestamps
    timezone_offset = None
    timezone_indicators = ['last_updated', 'last_token_update', 'updated_at', 'next_notification_time']
    
    for field in timezone_indicators:
        if field in user_data and user_data[field]:
            timestamp_value = user_data[field]
            # Check if the timestamp has timezone information
            if hasattr(timestamp_value, 'tzinfo') and timestamp_value.tzinfo:
                timezone_offset = timestamp_value.utcoffset().total_seconds() / 3600
                logger.info(f"Found user timezone offset from {field}: UTC{'+' if timezone_offset >= 0 else ''}{timezone_offset}")
                break
    
    # Default to UTC if we couldn't determine timezone
    if timezone_offset is None:
        logger.warning("Could not determine user timezone, defaulting to UTC")
        timezone_offset = 0
        
    return timezone_offset

def calculate_next_notification_time(hour, minute, user_timezone_offset, current_time=None):
    """
    Calculate the next notification time in UTC based on user's preferred local time.
    
    Args:
        hour: User's preferred hour (in their local timezone)
        minute: User's preferred minute
        user_timezone_offset: User's timezone offset from UTC (in hours)
        current_time: Current time (defaults to now if not provided)
    
    Returns:
        next_time: The next notification time as a datetime object in UTC
    """
    # Use provided time or current UTC time
    now = current_time or datetime.now(timezone.utc)
    logger.info(f"Current time (UTC): {now.isoformat()}")
    
    # First, convert the current UTC time to the user's local time
    user_local_time = now.astimezone(timezone(timedelta(hours=user_timezone_offset)))
    logger.info(f"Current time in user's timezone (UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}): {user_local_time.isoformat()}")
    
    # Create a base date in the user's timezone (today at midnight)
    user_base_date = user_local_time.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Create the target time in user's local timezone
    user_target_time = user_base_date.replace(hour=hour, minute=minute)
    logger.info(f"Target time in user's timezone: {user_target_time.isoformat()}")
    
    # If target time has passed in user's timezone, add a day
    if user_target_time <= user_local_time:
        user_target_time += timedelta(days=1)
        logger.info(f"Target time already passed in user's timezone, scheduling for tomorrow: {user_target_time.isoformat()}")
        
    # Convert the final time back to UTC for storage and scheduling
    target_time_utc = user_target_time.astimezone(timezone.utc)
    logger.info(f"Final notification time (UTC): {target_time_utc.isoformat()}")
    
    return target_time_utc
