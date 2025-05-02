# update_information/main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone, time
import json
import uuid
import requests

# Initialize Firebase Admin if not already initialized
try:
    app = firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()

db = firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.http
def update_information(request):
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
        
        if not user_id:
            return (json.dumps({'error': 'Missing user_id'}), 400, headers)
        
        # Check if user exists
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        # Get user data for timezone information
        user_data = user_doc.to_dict()
        
        # Get update data
        notification_time = request_json.get('notification_time')
        next_notification_time_input = request_json.get('next_notification_time')
        user_goals = request_json.get('user_goals')
        exercise_routine = request_json.get('exercise_routine')
        user_timezone_input = request_json.get('timezone')
        force_today = request_json.get('force_today', False)  # New flag to force notification for today
        
        # Prepare update data
        update_data = {}
        notification_updated = False
        
        # Determine user timezone from existing timestamps or from request
        user_timezone_offset_hours = None
        if user_timezone_input:
            try:
                # Client provided timezone as hours offset (e.g., -7 for UTC-7)
                user_timezone_offset_hours = float(user_timezone_input)
                print(f"Using client-provided timezone: UTC{'+' if user_timezone_offset_hours >= 0 else ''}{user_timezone_offset_hours}")
            except (ValueError, TypeError):
                print(f"Invalid timezone format provided: {user_timezone_input}")
        
        # Try to get timezone from existing timestamps if not provided
        if user_timezone_offset_hours is None:
            timezone_indicators = ['last_updated', 'last_token_update', 'updated_at', 'next_notification_time']
            for field in timezone_indicators:
                if field in user_data and user_data[field]:
                    timestamp_value = user_data[field]
                    # Check if the timestamp has timezone information
                    if hasattr(timestamp_value, 'tzinfo') and timestamp_value.tzinfo:
                        user_timezone_offset_hours = timestamp_value.utcoffset().total_seconds() / 3600
                        print(f"Found user timezone offset from {field}: UTC{'+' if user_timezone_offset_hours >= 0 else ''}{user_timezone_offset_hours}")
                        break
        
        # Default to UTC if we still couldn't determine timezone
        if user_timezone_offset_hours is None:
            print("Could not determine user timezone, defaulting to UTC")
            user_timezone_offset_hours = 0
        
        # Create the timezone object
        user_tz = timezone(timedelta(hours=user_timezone_offset_hours))
        
        # Update notification preferences if provided
        if notification_time:
            try:
                # Parse notification time (expected format: "HH:MM")
                hour, minute = map(int, notification_time.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    update_data['notification_preferences'] = {
                        'is_enabled': True,
                        'frequency': 'daily',  # Default to daily
                        'hour': hour,
                        'minute': minute,
                        'updated_at': firestore.SERVER_TIMESTAMP,
                        'updated_by': 'elevenlabs_agent',
                        'last_scheduled_utc': None
                    }
                    notification_updated = True
                    print(f"Prepared update for notification_preferences: HH:MM {hour:02d}:{minute:02d}")
                else:
                    print(f"Invalid hour/minute range in notification_time: {notification_time}")
                    return (json.dumps({'error': 'Invalid notification time format (range)'}), 400, headers)
            except (ValueError, AttributeError):
                print(f"Failed to parse notification_time: {notification_time}")
                return (json.dumps({'error': 'Invalid notification time format (parsing)'}), 400, headers)
        
        # Update next notification time if provided
        if next_notification_time_input:
            try:
                hour, minute = map(int, next_notification_time_input.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    # Get current time IN USER'S TIMEZONE
                    now_user_tz = datetime.now(user_tz)

                    # Create target time for TODAY in user's timezone
                    target_time_today = now_user_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)

                    # If the target time has already passed today, schedule for tomorrow
                    # unless force_today is True
                    if target_time_today <= now_user_tz and not force_today:
                        target_datetime = target_time_today + timedelta(days=1)
                        print(f"Target time {hour:02d}:{minute:02d} already passed today in user TZ. Scheduling for tomorrow.")
                    else:
                        target_datetime = target_time_today
                        if target_time_today <= now_user_tz and force_today:
                            print(f"Target time {hour:02d}:{minute:02d} already passed today, but force_today=True. Scheduling for today anyway.")
                        else:
                            print(f"Target time {hour:02d}:{minute:02d} is later today in user TZ. Scheduling for today.")

                    # Convert to UTC for storage
                    target_time_utc = target_datetime.astimezone(timezone.utc)
                    
                    # Store without timezone info
                    utc_datetime_no_tzinfo = datetime(
                        target_time_utc.year, 
                        target_time_utc.month,
                        target_time_utc.day,
                        target_time_utc.hour,
                        target_time_utc.minute,
                        target_time_utc.second
                    )
                    
                    # Set the one-time flag
                    is_one_time = True
                    
                    # Store both the time and the one-time flag
                    update_data['next_notification_time'] = utc_datetime_no_tzinfo
                    update_data['next_notification_time_utc'] = utc_datetime_no_tzinfo.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    update_data['next_notification_utc_hour'] = utc_datetime_no_tzinfo.hour
                    update_data['next_notification_utc_minute'] = utc_datetime_no_tzinfo.minute
                    update_data['is_one_time_notification'] = is_one_time
                    # Track if this was forced to be today
                    if force_today:
                        update_data['force_today'] = True
                    
                    local_hour = hour 
                    local_minute = minute
                    print(f"✅ This will be {local_hour:02d}:{local_minute:02d} in the user's local timezone")

                else:
                    print(f"Invalid hour/minute range in next_notification_time: {next_notification_time_input}")
                    return (json.dumps({'error': 'Invalid next notification time format (range)'}), 400, headers)
            except (ValueError, AttributeError):
                print(f"Failed to parse next_notification_time: {next_notification_time_input}")
                return (json.dumps({'error': 'Invalid next notification time format (parsing)'}), 400, headers)
        
        # Update user goals if provided
        if user_goals:
            update_data['user_goals'] = user_goals
            update_data['goal_updated_at'] = firestore.SERVER_TIMESTAMP
            update_data['goal_updated_by'] = 'elevenlabs_agent'
        
        # Update exercise routine if provided
        if exercise_routine:
            # Validate exercise routine format - should be a string
            if not isinstance(exercise_routine, str):
                return (json.dumps({'error': 'Exercise routine must be a string describing your regular physical activities'}), 400, headers)
            
            # Update the exercise routine
            update_data['exercise_routine'] = exercise_routine
            update_data['routine_updated_at'] = firestore.SERVER_TIMESTAMP
            update_data['routine_updated_by'] = 'elevenlabs_agent'
        
        # If no updates provided
        if not update_data:
            return (json.dumps({'error': 'No update data provided'}), 400, headers)
        
        # Update user document
        print(f"Updating Firestore for user {user_id} with data: {update_data}")
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
        
        # If notification time was updated, schedule a notification
        scheduled_task_id = None
        
        if notification_updated:
            # Use the standardized function to calculate next notification time
            next_time = calculate_next_notification_time(
                hour=update_data['notification_preferences']['hour'],
                minute=update_data['notification_preferences']['minute'],
                user_timezone_offset=user_timezone_offset_hours
            )
            
            # Update the user's next_notification_time
            user_ref.update({
                'next_notification_time': next_time,
                'next_notification_time_utc': next_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                'next_notification_utc_hour': next_time.hour,
                'next_notification_utc_minute': next_time.minute
            })
            
            # Cancel any existing scheduled notifications
            try:
                cancel_existing_scheduled_notifications(user_id)
            except Exception as e:
                print(f"Error cancelling existing notifications: {str(e)}")
            
            # Schedule the next notification
            try:
                is_one_time = True if next_notification_time_input else False
                task_response = schedule_notification_task(
                    user_id,
                    next_time.isoformat(),
                    is_one_time=is_one_time,
                    force_today=force_today
                )
                if task_response and 'notification_id' in task_response:
                    scheduled_task_id = task_response['notification_id']
            except Exception as e:
                print(f"Error scheduling new notification: {str(e)}")
        
        response_data = {
            'status': 'success',
            'message': 'User information updated successfully',
            'updated_values': update_data
        }
        
        if scheduled_task_id:
            response_data['scheduled_notification_id'] = scheduled_task_id
            
        if notification_updated:
            print("Recurring notification preferences updated. Consider triggering schedule update.")
            if 'next_notification_time' in update_data:
                print(f"Specific next notification time set to {update_data['next_notification_time']}. Ensure scheduler handles this.")
            
        return (json.dumps(response_data), 200, headers)
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error updating user information: {str(e)}\n{error_details}")
        return (json.dumps({'error': str(e)}), 500, headers)

def cancel_existing_scheduled_notifications(user_id):
    """Cancel any existing scheduled notifications for the user."""
    # Get notifications with status 'scheduled'
    notifications = db.collection('notifications') \
        .where('user_id', '==', user_id) \
        .where('status', '==', 'scheduled') \
        .stream()
    
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
                # We could use the Cloud Tasks client here to delete the task
                from google.cloud import tasks_v2
                client = tasks_v2.CloudTasksClient()
                client.delete_task(name=task_name)
                print(f"Deleted Cloud Task: {task_name}")
            except Exception as e:
                print(f"Error deleting Cloud Task {task_name}: {str(e)}")

def schedule_notification_task(user_id, scheduled_time, is_one_time=False, custom_title=None, custom_body=None, force_today=False):
    """Call the schedule_notification Cloud Function."""
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
    print(f"Sending notification schedule request with payload: {json.dumps(payload)}")
    
    # Make the HTTP request
    response = requests.post(url, json=payload)
    
    # Process the response
    print(f"Schedule API response status: {response.status_code}")
    
    if response.status_code == 200:
        try:
            response_data = response.json()
            print(f"Schedule API success: {json.dumps(response_data)}")
            return response_data
        except json.JSONDecodeError:
            error_message = f"Failed to parse API response as JSON: {response.text}"
            print(error_message)
            raise Exception(error_message)
    else:
        error_message = f"Failed to schedule notification: HTTP {response.status_code}: {response.text}"
        print(error_message)
        try:
            error_json = response.json()
            print(f"Error details: {json.dumps(error_json)}")
        except:
            print(f"Could not parse error response as JSON")
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
    print(f"Current time (UTC): {now.isoformat()}")
    
    # First, convert the current UTC time to the user's local time
    user_local_time = now.astimezone(timezone(timedelta(hours=user_timezone_offset)))
    print(f"Current time in user's timezone (UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}): {user_local_time.isoformat()}")
    
    # Create a base date in the user's timezone (today at midnight)
    user_base_date = user_local_time.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Create the target time in user's local timezone
    user_target_time = user_base_date.replace(hour=hour, minute=minute)
    print(f"Target time in user's timezone: {user_target_time.isoformat()}")
    
    # If target time has passed in user's timezone, add a day
    if user_target_time <= user_local_time:
        user_target_time += timedelta(days=1)
        print(f"Target time already passed in user's timezone, scheduling for tomorrow: {user_target_time.isoformat()}")
        
    # Convert the final time back to UTC for storage and scheduling
    target_time_utc = user_target_time.astimezone(timezone.utc)
    print(f"Final notification time (UTC): {target_time_utc.isoformat()}")
    
    # *** FIX: Store as a native datetime without timezone info for Firestore ***
    # Firestore can handle timezone-aware datetimes properly, but let's explicitly create a
    # UTC datetime without timezone info to guarantee consistent behavior across different clients
    utc_datetime_no_tzinfo = datetime(
        target_time_utc.year,
        target_time_utc.month,
        target_time_utc.day,
        target_time_utc.hour,
        target_time_utc.minute,
        target_time_utc.second,
        target_time_utc.microsecond
    )
    
    # Create explicit UTC string representation
    utc_time_str = utc_datetime_no_tzinfo.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    print(f"Converted to UTC datetime without timezone info: {utc_datetime_no_tzinfo.isoformat()}Z")
    print(f"UTC string representation: {utc_time_str}")
    print(f"This will be {hour:02d}:{minute:02d} in the user's local timezone (UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset})")
    
    # Return the UTC datetime without timezone info
    return utc_datetime_no_tzinfo

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
         # Handle Firestore Timestamp objects if they appear (though update_data shouldn't have them yet)
         return data.datetime.isoformat()
    # Skip Firestore SERVER_TIMESTAMP placeholder or other non-serializable types if necessary
    elif isinstance(data, type(firestore.SERVER_TIMESTAMP)):
         return None # Or return a placeholder string like "SERVER_TIMESTAMP"
    else:
        # Return other basic types as is
        return data