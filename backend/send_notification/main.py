# send_notification/main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
import json
from datetime import datetime, timezone, timedelta
import requests

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
        
        # Validate required parameters
        if not notification_id or not user_id:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get notification data
        notification_ref = db.collection('notifications').document(notification_id)
        notification_doc = notification_ref.get()
        
        if not notification_doc.exists:
            return (json.dumps({'error': 'Notification not found'}), 404, headers)
        
        notification_data = notification_doc.to_dict()
        
        # Check if notification was already sent or cancelled
        status = notification_data.get('status')
        if status == 'sent':
            return (json.dumps({
                'status': 'warning',
                'message': 'Notification was already sent'
            }), 200, headers)
        elif status == 'cancelled':
            return (json.dumps({
                'status': 'warning',
                'message': 'Notification was cancelled'
            }), 200, headers)
        
        # Get user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
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
            notification_ref.update({
                'status': 'failed',
                'error': 'No FCM token for user',
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            return (json.dumps({'error': 'No FCM token for user'}), 400, headers)
        
        # Get notification content - prioritize next_day_notification content
        username = user_data.get('name', 'User')
        next_day_data = user_data.get('next_day_notification', {})
        stored_content = notification_data.get('content', {})
        
        # Get content from next_day_notification if available
        if next_day_data and 'title' in next_day_data and 'body' in next_day_data:
            notification_title = next_day_data.get('title')
            notification_body = next_day_data.get('body')
        else:
            # Fallback to content saved with the notification
            notification_title = stored_content.get('title', f"Time for Exercise, {username}!")
            notification_body = stored_content.get('body', "It's time for your daily exercise routine. Let's keep that streak going!")
        
        # Get user preferences for iOS configuration
        device_type = user_data.get('device_type', 'unknown')
        bundle_id = user_data.get('app_bundle_id', 'com.pepmvp.app')
        
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
            response = messaging.send(message)
            
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
                # Get notification preferences
                notification_prefs = user_data.get('notification_preferences', {})
                if notification_prefs.get('is_enabled', False) and notification_prefs.get('frequency') == 'daily':
                    hour = notification_prefs.get('hour')
                    minute = notification_prefs.get('minute')
                    
                    if hour is not None and minute is not None:
                        # Get user's timezone offset
                        user_timezone_offset = get_user_timezone_offset(user_data)
                        print(f"User timezone offset: UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}")
                        
                        # Calculate next notification time using the standardized function
                        next_time = calculate_next_notification_time(
                            hour=hour,
                            minute=minute,
                            user_timezone_offset=user_timezone_offset
                        )
                        
                        # Update user's next notification time
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
                            
                            # Log the payload
                            print(f"Scheduling next notification with payload: {json.dumps(payload)}")
                            
                            # Make the HTTP request
                            schedule_response = requests.post(url, json=payload)
                            
                            if schedule_response.status_code == 200:
                                response_data = schedule_response.json()
                                print(f"Successfully scheduled next notification: {json.dumps(response_data)}")
                            else:
                                print(f"Failed to schedule next notification: {schedule_response.text}")
                        except Exception as schedule_error:
                            print(f"Error scheduling next notification: {str(schedule_error)}")
            
            return (json.dumps({
                'status': 'success',
                'message': 'Notification sent successfully',
                'fcm_message_id': response
            }), 200, headers)
            
        except messaging.ApiCallError as fcm_error:
            error_msg = str(fcm_error)
            
            # Handle invalid token
            if 'registration-token-not-registered' in error_msg.lower():
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
                'message': f'FCM API Error: {error_msg}'
            }), 500, headers)
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error sending notification: {str(e)}\n{error_details}")
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

# Helper function to determine user timezone
def get_user_timezone_offset(user_data):
    """Extract timezone offset from user data timestamps."""
    timezone_offset = None
    timezone_indicators = ['last_updated', 'last_token_update', 'updated_at', 'next_notification_time']
    
    for field in timezone_indicators:
        if field in user_data and user_data[field]:
            timestamp_value = user_data[field]
            # Check if the timestamp has timezone information
            if hasattr(timestamp_value, 'tzinfo') and timestamp_value.tzinfo:
                timezone_offset = timestamp_value.utcoffset().total_seconds() / 3600
                print(f"Found user timezone offset from {field}: UTC{'+' if timezone_offset >= 0 else ''}{timezone_offset}")
                break
    
    # Default to UTC if we couldn't determine timezone
    if timezone_offset is None:
        print("Could not determine user timezone, defaulting to UTC")
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
    print(f"Current time (UTC): {now.isoformat()}")
    
    # Convert user's preferred hour to UTC
    user_hour_in_utc = hour - user_timezone_offset
    print(f"User's {hour}:{minute} in their timezone is {user_hour_in_utc}:{minute} in UTC")
    
    # Handle hour wrapping around 24-hour cycle
    hour_in_utc = int(user_hour_in_utc) % 24
    
    # Start with today as the base date
    base_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Determine if we need to adjust the day
    day_offset = 0
    
    # If the hour conversion puts us in the previous day
    if user_hour_in_utc < 0:
        day_offset = 1
    
    # Create the target notification time
    target_time = base_date + timedelta(days=day_offset, hours=hour_in_utc, minutes=minute)
    print(f"Initial target time (UTC): {target_time.isoformat()}")
    
    # If the target time has already passed today, schedule for tomorrow
    if target_time <= now:
        target_time += timedelta(days=1)
        print(f"Time today has passed, scheduling for tomorrow: {target_time.isoformat()}")
        
    print(f"Final notification time (UTC): {target_time.isoformat()}")
    
    # Calculate what this time would be in the user's timezone (for logging only)
    user_local_time = target_time.astimezone(timezone(timedelta(hours=user_timezone_offset)))
    print(f"This equals {user_local_time.strftime('%Y-%m-%d %H:%M:%S')} in user's local timezone (UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset})")
    
    return target_time