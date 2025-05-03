import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
import json
from datetime import datetime, timezone, timedelta
import requests
import logging
import traceback

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
        user_id = request_json.get('user_id')
        
        logger.info(f"Received request to send notification {notification_id} for user {user_id}")
        
        # Validate required parameters
        if not notification_id or not user_id:
            logger.error("Missing required parameters: notification_id or user_id")
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get notification data
        notification_ref = db.collection('notifications').document(notification_id)
        notification_doc = notification_ref.get()
        
        if not notification_doc.exists:
            logger.error(f"Notification {notification_id} not found")
            return (json.dumps({'error': 'Notification not found'}), 404, headers)
        
        notification_data = notification_doc.to_dict()
        
        # Check if notification was already sent or cancelled
        status = notification_data.get('status')
        if status == 'sent':
            logger.warning(f"Notification {notification_id} was already sent")
            return (json.dumps({
                'status': 'warning',
                'message': 'Notification was already sent'
            }), 200, headers)
        elif status == 'cancelled':
            logger.warning(f"Notification {notification_id} was cancelled")
            return (json.dumps({
                'status': 'warning',
                'message': 'Notification was cancelled'
            }), 200, headers)
        
        # Get user data
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
        
        # Log for verification
        logger.info(f"Found FCM token for user {user_id}: {fcm_token[:10]}...")
        
        # Get notification content - prioritize next_day_notification content
        username = user_data.get('name', 'User')
        next_day_data = user_data.get('next_day_notification', {})
        stored_content = notification_data.get('content', {})
        
        # Get content from next_day_notification if available
        if next_day_data and 'title' in next_day_data and 'body' in next_day_data:
            notification_title = next_day_data.get('title')
            notification_body = next_day_data.get('body')
            logger.info(f"Using next_day_notification content for user {user_id}")
        else:
            # Fallback to content saved with the notification
            notification_title = stored_content.get('title', f"Time for Exercise, {username}!")
            notification_body = stored_content.get('body', "It's time for your daily exercise routine. Let's keep that streak going!")
            logger.info(f"Using stored notification content for user {user_id}")
        
        # Log notification content
        logger.info(f"Notification content: title='{notification_title}', body='{notification_body}'")
        
        # Get user preferences for iOS configuration
        device_type = user_data.get('device_type', 'unknown')
        bundle_id = user_data.get('app_bundle_id', 'com.pepmvp.app')
        
        logger.info(f"User {user_id} device type: {device_type}, bundle ID: {bundle_id}")
        
        # APNS configuration for iOS
        if device_type and device_type.lower() == 'ios':
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
            logger.info(f"Created iOS APNS config with bundle ID: {bundle_id}")
        else:
            # Default configuration for other devices
            apns_config = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1,
                        content_available=True
                    )
                )
            )
            logger.info(f"Created default APNS config for non-iOS device")
        
        # Compose FCM message
        message = messaging.Message(
            notification=messaging.Notification(
                title=notification_title,
                body=notification_body
            ),
            data={
                'notification_id': notification_id,
                'user_id': user_id,
                'type': notification_data.get('type', 'exercise_reminder')
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
        
        # Send the notification
        try:
            logger.info(f"Sending FCM notification to user {user_id}")
            response = messaging.send(message)
            logger.info(f"FCM notification sent successfully: {response}")
            
            # Update notification status
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
            if not is_one_time:
                logger.info(f"Processing recurring notification for user {user_id}")
                # Get notification preferences
                notification_prefs = user_data.get('notification_preferences', {})
                if notification_prefs.get('is_enabled', False) and notification_prefs.get('frequency') == 'daily':
                    hour = notification_prefs.get('hour')
                    minute = notification_prefs.get('minute')
                    
                    if hour is not None and minute is not None:
                        # Get user's timezone offset using the standardized function
                        user_timezone_offset = extract_timezone_offset(user_data)
                        logger.info(f"User {user_id} timezone offset: UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}")
                        
                        # Calculate next notification time
                        next_time = calculate_next_notification_time(
                            hour=hour,
                            minute=minute,
                            user_timezone_offset=user_timezone_offset
                        )
                        
                        logger.info(f"Calculated next notification time (UTC): {next_time.isoformat()}")
                        
                        # Update user's next notification time
                        user_ref.update({
                            'next_notification_time': next_time,
                            'next_notification_time_utc': next_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                            'next_notification_utc_hour': next_time.hour,
                            'next_notification_utc_minute': next_time.minute
                        })
                        
                        # Schedule the next notification through a separate HTTP call
                        try:
                            # Prepare the request payload
                            payload = {
                                'user_id': user_id,
                                'scheduled_time': next_time.isoformat(),
                                'is_one_time': False
                            }
                            
                            # URL of the schedule_notification Cloud Function
                            url = f"https://us-central1-pepmvp.cloudfunctions.net/schedule_notification"
                            
                            # Log the payload
                            logger.info(f"Scheduling next notification with payload: {json.dumps(payload)}")
                            
                            # Make the HTTP request
                            schedule_response = requests.post(url, json=payload, timeout=30)
                            
                            if schedule_response.status_code == 200:
                                response_data = schedule_response.json()
                                logger.info(f"Successfully scheduled next notification: {json.dumps(response_data)}")
                            else:
                                logger.error(f"Failed to schedule next notification: {schedule_response.text}")
                                logger.error(f"Status code: {schedule_response.status_code}")
                        except Exception as schedule_error:
                            logger.error(f"Error scheduling next notification: {str(schedule_error)}")
                            logger.error(traceback.format_exc())
                else:
                    logger.warning(f"Recurring notification not scheduled: is_enabled={notification_prefs.get('is_enabled')}, frequency={notification_prefs.get('frequency')}")
            else:
                logger.info(f"Notification {notification_id} was one-time, not scheduling next one")
            
            return (json.dumps({
                'status': 'success',
                'message': 'Notification sent successfully',
                'fcm_message_id': response
            }), 200, headers)
            
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError) as token_error:
            # Handle invalid token errors
            error_msg = str(token_error)
            logger.error(f"FCM Token error for user {user_id}: {error_msg}")
            
            user_ref.update({
                'fcm_token': firestore.DELETE_FIELD,
                'notification_status': 'token_expired'
            })
            
            # Update notification record
            notification_ref.update({
                'status': 'failed',
                'error': error_msg,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            return (json.dumps({
                'status': 'error',
                'message': f'FCM Token Error: {error_msg}'
            }), 500, headers)
            
        except firebase_admin._messaging_utils.ThirdPartyAuthError as auth_error:
            # Handle authentication errors with FCM
            error_msg = f"Firebase authentication error: {str(auth_error)}"
            logger.error(error_msg)
            
            # Update notification record
            notification_ref.update({
                'status': 'failed',
                'error': error_msg,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            return (json.dumps({
                'status': 'error',
                'message': error_msg
            }), 500, headers)
            
        except Exception as fcm_error:
            # Handle all other FCM errors
            error_msg = str(fcm_error)
            logger.error(f"FCM general error: {error_msg}")
            logger.error(traceback.format_exc())
            
            # Update notification record
            notification_ref.update({
                'status': 'failed',
                'error': error_msg,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            return (json.dumps({
                'status': 'error',
                'message': f'Notification Error: {error_msg}'
            }), 500, headers)
            
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error sending notification: {str(e)}\n{error_details}")
        return (json.dumps({'error': str(e)}), 500, headers)

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
    
    # Create a target time in user's local timezone for today
    user_target_time = user_local_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    logger.info(f"Target time in user's timezone: {user_target_time.isoformat()}")
    
    # If target time has passed in user's timezone, add a day
    if user_target_time <= user_local_time:
        user_target_time += timedelta(days=1)
        logger.info(f"Target time already passed in user's timezone, scheduling for tomorrow: {user_target_time.isoformat()}")
        
    # Convert the final time back to UTC for storage and scheduling
    target_time_utc = user_target_time.astimezone(timezone.utc)
    logger.info(f"Final notification time (UTC): {target_time_utc.isoformat()}")
    
    return target_time_utc

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