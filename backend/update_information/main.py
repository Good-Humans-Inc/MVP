import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone
import json
import uuid
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
def update_information(request):
    """
    Update user information and notification preferences.
    
    Expected request format:
    {
        "user_id": "string",
        "notification_time": "HH:MM", (optional)
        "next_notification_time": "HH:MM", (optional)
        "user_goals": "string", (optional)
        "exercise_routine": "string", (optional)
        "timezone": float or string, (optional)
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
        
        logger.info(f"Received update_information request for user {user_id}")
        
        if not user_id:
            logger.error("Missing user_id in request")
            return (json.dumps({'error': 'Missing user_id'}), 400, headers)
        
        # Check if user exists
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.error(f"User {user_id} not found")
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        # Get user data for timezone information
        user_data = user_doc.to_dict()
        
        # Get update data
        notification_time = request_json.get('notification_time')
        next_notification_time_input = request_json.get('next_notification_time')
        user_goals = request_json.get('user_goals')
        exercise_routine = request_json.get('exercise_routine')
        user_timezone_input = request_json.get('timezone')
        force_today = request_json.get('force_today', False)
        
        # Prepare update data
        update_data = {}
        notification_updated = False
        
        # Determine user timezone from input or existing data
        user_timezone_offset_hours = None
        if user_timezone_input is not None:
            try:
                # Client provided timezone as hours offset (e.g., -7 for UTC-7)
                user_timezone_offset_hours = float(user_timezone_input)
                logger.info(f"Using client-provided timezone: UTC{'+' if user_timezone_offset_hours >= 0 else ''}{user_timezone_offset_hours}")
                
                # Store timezone offset in user data
                update_data['notification_timezone_offset'] = user_timezone_offset_hours
            except (ValueError, TypeError):
                logger.error(f"Invalid timezone format provided: {user_timezone_input}")
        
        # If timezone not provided, extract from existing data
        if user_timezone_offset_hours is None:
            user_timezone_offset_hours = extract_timezone_offset(user_data)
            logger.info(f"Extracted timezone offset: UTC{'+' if user_timezone_offset_hours >= 0 else ''}{user_timezone_offset_hours}")
        
        # Create the timezone object
        user_tz = timezone(timedelta(hours=user_timezone_offset_hours))
        
        # Update notification preferences if provided
        if notification_time:
            try:
                # Parse notification time (expected format: "HH:MM")
                hour, minute = map(int, notification_time.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    logger.info(f"Setting notification preferences to {hour:02d}:{minute:02d} in user's local timezone")
                    
                    update_data['notification_preferences'] = {
                        'is_enabled': True,
                        'frequency': 'daily',  # Default to daily
                        'hour': hour,          # Local hour (what user sees)
                        'minute': minute,      # Local minute
                        'timezone_offset': user_timezone_offset_hours,
                        'updated_at': firestore.SERVER_TIMESTAMP,
                        'updated_by': 'elevenlabs_agent',
                        'last_scheduled_utc': None
                    }
                    notification_updated = True
                else:
                    logger.error(f"Invalid hour/minute range in notification_time: {notification_time}")
                    return (json.dumps({'error': 'Invalid notification time format (range)'}), 400, headers)
            except (ValueError, AttributeError):
                logger.error(f"Failed to parse notification_time: {notification_time}")
                return (json.dumps({'error': 'Invalid notification time format (parsing)'}), 400, headers)
        
        # Update next notification time if provided
        if next_notification_time_input:
            try:
                hour, minute = map(int, next_notification_time_input.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    logger.info(f"Processing one-time notification request for {hour:02d}:{minute:02d} in user's local timezone")
                    
                    # Get current time IN USER'S TIMEZONE
                    now_user_tz = datetime.now(user_tz)
                    logger.info(f"Current time in user timezone: {now_user_tz.isoformat()}")

                    # Create target time for TODAY in user's timezone
                    target_time_today = now_user_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    logger.info(f"Target time today in user timezone: {target_time_today.isoformat()}")

                    # If the target time has already passed today and force_today is False, schedule for tomorrow
                    if target_time_today <= now_user_tz and not force_today:
                        target_datetime = target_time_today + timedelta(days=1)
                        logger.info(f"Target time already passed today in user TZ. Scheduling for tomorrow.")
                    else:
                        target_datetime = target_time_today
                        if target_time_today <= now_user_tz and force_today:
                            logger.info(f"Target time already passed today, but force_today=True. Scheduling for today anyway.")
                        else:
                            logger.info(f"Target time is later today in user TZ. Scheduling for today.")

                    # Convert to UTC for storage
                    target_time_utc = target_datetime.astimezone(timezone.utc)
                    logger.info(f"Converted target time to UTC: {target_time_utc.isoformat()}")
                    
                    # Store time as UTC in database
                    update_data['next_notification_time'] = target_time_utc
                    update_data['next_notification_time_utc'] = target_time_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    update_data['next_notification_utc_hour'] = target_time_utc.hour
                    update_data['next_notification_utc_minute'] = target_time_utc.minute
                    update_data['next_notification_local_hour'] = hour
                    update_data['next_notification_local_minute'] = minute
                    update_data['notification_timezone_offset'] = user_timezone_offset_hours
                    update_data['next_notification_time_manual_override'] = True
                    
                    # Track if this was forced to be today
                    if force_today:
                        update_data['force_today'] = True
                        logger.info("Setting force_today flag for this notification")

                else:
                    logger.error(f"Invalid hour/minute range in next_notification_time: {next_notification_time_input}")
                    return (json.dumps({'error': 'Invalid next notification time format (range)'}), 400, headers)
            except (ValueError, AttributeError):
                logger.error(f"Failed to parse next_notification_time: {next_notification_time_input}")
                return (json.dumps({'error': 'Invalid next notification time format (parsing)'}), 400, headers)
        
        # Update user goals if provided
        if user_goals:
            update_data['user_goals'] = user_goals
            update_data['goal_updated_at'] = firestore.SERVER_TIMESTAMP
            update_data['goal_updated_by'] = 'elevenlabs_agent'
            logger.info(f"Updating user goals for user {user_id}")
        
        # Update exercise routine if provided
        if exercise_routine:
            # Validate exercise routine format - should be a string
            if not isinstance(exercise_routine, str):
                logger.error("Exercise routine must be a string")
                return (json.dumps({'error': 'Exercise routine must be a string describing your regular physical activities'}), 400, headers)
            
            # Update the exercise routine
            update_data['exercise_routine'] = exercise_routine
            update_data['routine_updated_at'] = firestore.SERVER_TIMESTAMP
            update_data['routine_updated_by'] = 'elevenlabs_agent'
            logger.info(f"Updating exercise routine for user {user_id}")
        
        # If no updates provided
        if not update_data:
            logger.warning("No update data provided")
            return (json.dumps({'error': 'No update data provided'}), 400, headers)
        
        # Update user document
        logger.info(f"Updating Firestore for user {user_id} with data: {update_data}")
        user_ref.update(update_data)
        
        # Create an activity log entry
        activity_id = str(uuid.uuid4())
        activity_data = {
            'id': activity_id,
            'user_id': user_id,
            'type': 'profile_update',
            'updated_fields': list(update_data.keys()),
            'updated_at': firestore.SERVER_TIMESTAMP,
            'updated_by': 'elevenlabs_agent'
        }
        
        db.collection('activities').document(activity_id).set(activity_data)
        logger.info(f"Created activity log entry {activity_id} for user {user_id}")
        
        # If notification time was updated, schedule a notification
        scheduled_task_id = None
        
        if notification_updated:
            logger.info("Notification preferences were updated, scheduling next notification")
            # Use the standardized function to calculate next notification time
            next_time = calculate_next_notification_time(
                hour=update_data['notification_preferences']['hour'],
                minute=update_data['notification_preferences']['minute'],
                user_timezone_offset=user_timezone_offset_hours
            )
            
            logger.info(f"Calculated next notification time (UTC): {next_time.isoformat()}")
            
            # Update the user's next_notification_time
            user_ref.update({
                'next_notification_time': next_time,
                'next_notification_time_utc': next_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                'next_notification_utc_hour': next_time.hour,
                'next_notification_utc_minute': next_time.minute,
                'notification_timezone_offset': user_timezone_offset_hours
            })
            
            # Cancel any existing scheduled notifications
            try:
                logger.info(f"Cancelling existing scheduled notifications for user {user_id}")
                cancel_existing_scheduled_notifications(user_id)
            except Exception as e:
                logger.error(f"Error cancelling existing notifications: {str(e)}")
                logger.error(traceback.format_exc())
            
            # Schedule the next notification
            try:
                is_one_time = True if next_notification_time_input else False
                logger.info(f"Scheduling new notification for user {user_id}: is_one_time={is_one_time}, force_today={force_today}")
                task_response = schedule_notification_task(
                    user_id,
                    next_time.isoformat(),
                    is_one_time=is_one_time,
                    force_today=force_today
                )
                if task_response and 'notification_id' in task_response:
                    scheduled_task_id = task_response['notification_id']
                    logger.info(f"Scheduled notification with ID: {scheduled_task_id}")
            except Exception as e:
                logger.error(f"Error scheduling new notification: {str(e)}")
                logger.error(traceback.format_exc())
        elif next_notification_time_input:
            logger.info("One-time notification time was set, scheduling notification")
            # Extract the one-time notification time from update_data
            next_time = update_data.get('next_notification_time')
            
            # Cancel any existing scheduled notifications
            try:
                logger.info(f"Cancelling existing scheduled notifications for user {user_id}")
                cancel_existing_scheduled_notifications(user_id)
            except Exception as e:
                logger.error(f"Error cancelling existing notifications: {str(e)}")
                logger.error(traceback.format_exc())
            
            # Schedule the one-time notification
            try:
                logger.info(f"Scheduling one-time notification for user {user_id}")
                task_response = schedule_notification_task(
                    user_id,
                    next_time.isoformat(),
                    is_one_time=True,
                    force_today=force_today
                )
                if task_response and 'notification_id' in task_response:
                    scheduled_task_id = task_response['notification_id']
                    logger.info(f"Scheduled one-time notification with ID: {scheduled_task_id}")
            except Exception as e:
                logger.error(f"Error scheduling one-time notification: {str(e)}")
                logger.error(traceback.format_exc())
        
        response_data = {
            'status': 'success',
            'message': 'User information updated successfully',
            'updated_values': serialize_firestore_data(update_data)
        }
        
        if scheduled_task_id:
            response_data['scheduled_notification_id'] = scheduled_task_id
            
        return (json.dumps(response_data), 200, headers)
            
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error updating user information: {str(e)}\n{error_details}")
        return (json.dumps({'error': str(e)}), 500, headers)

def extract_timezone_offset(user_data):
    """Extract timezone offset from user data consistently."""
    # First, try to get from notification_preferences
    notification_prefs = user_data.get('notification_preferences', {})
    timezone_offset = notification_prefs.get('timezone_offset')
    
    # If not there, try notification_timezone_offset
    if timezone_offset is None:
        timezone_offset = user_data.get('notification_timezone_offset')
    
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

def cancel_existing_scheduled_notifications(user_id):
    """Cancel any existing scheduled notifications for the user."""
    logger.info(f"Cancelling existing scheduled notifications for user {user_id}")
    
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
        logger.info(f"Cancelled notification {notif.id}")
        
        # If we have task_name, try to delete the Cloud Task
        if task_name:
            try:
                # We could use the Cloud Tasks client here to delete the task
                from google.cloud import tasks_v2
                client = tasks_v2.CloudTasksClient()
                client.delete_task(name=task_name)
                logger.info(f"Deleted Cloud Task: {task_name}")
            except Exception as e:
                logger.error(f"Error deleting Cloud Task {task_name}: {str(e)}")
                logger.error(traceback.format_exc())
        
        cancelled_count += 1
    
    logger.info(f"Cancelled {cancelled_count} notifications for user {user_id}")
    return cancelled_count

def schedule_notification_task(user_id, scheduled_time, is_one_time=False, custom_title=None, custom_body=None, force_today=False):
    """Call the schedule_notification Cloud Function."""
    logger.info(f"Scheduling notification for user {user_id}: is_one_time={is_one_time}, force_today={force_today}")
    
    # Get the GCP project ID
    project_id = 'pepmvp'  # Your GCP project ID
    
    # Prepare the request payload
    payload = {
        'user_id': user_id,
        'scheduled_time': scheduled_time,
        'is_one_time': is_one_time,
        'force_today': force_today
    }
    
    if custom_title:
        payload['custom_title'] = custom_title
    
    if custom_body:
        payload['custom_body'] = custom_body
    
    # URL of the schedule_notification Cloud Function
    url = f"https://us-central1-{project_id}.cloudfunctions.net/schedule_notification"
    
    # Log the payload for debugging
    logger.info(f"Sending notification schedule request with payload: {json.dumps(payload)}")
    
    # Make the HTTP request with a timeout
    response = requests.post(url, json=payload, timeout=30)
    
    # Process the response
    logger.info(f"Schedule API response status: {response.status_code}")
    
    if response.status_code == 200:
        try:
            response_data = response.json()
            logger.info(f"Schedule API success: {json.dumps(response_data)}")
            return response_data
        except json.JSONDecodeError:
            error_message = f"Failed to parse API response as JSON: {response.text}"
            logger.error(error_message)
            raise Exception(error_message)
    else:
        error_message = f"Failed to schedule notification: HTTP {response.status_code}: {response.text}"
        logger.error(error_message)
        try:
            error_json = response.json()
            logger.error(f"Error details: {json.dumps(error_json)}")
        except:
            logger.error(f"Could not parse error response as JSON")
        raise Exception(error_message)

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
    
    # Create target time in user's local timezone for today
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
    """Helper function to serialize Firestore data for JSON, converting datetimes."""
    if isinstance(data, dict):
        # Recursively serialize dictionary values
        return {k: serialize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        # Recursively serialize list items
        return [serialize_firestore_data(item) for item in data]
    elif isinstance(data, datetime):
        # Convert datetime objects to ISO 8601 string format
        return data.isoformat()
    elif hasattr(data, 'datetime') and isinstance(getattr(data, 'datetime', None), datetime):
         # Handle Firestore Timestamp objects
         return data.datetime.isoformat()
    # Skip Firestore SERVER_TIMESTAMP placeholder or other non-serializable types
    elif isinstance(data, type(firestore.SERVER_TIMESTAMP)):
         return None
    else:
        # Return other basic types as is
        return data