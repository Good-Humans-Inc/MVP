import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore
import json
import requests
from datetime import datetime, timedelta, timezone
import sys
import traceback
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin
try:
    app = firebase_admin.get_app()
except ValueError:
    app = firebase_admin.initialize_app()

# Create Firestore client
db = admin_firestore.Client(project='pepmvp', database='pep-mvp')

def extract_document_path(cloud_event):
    """Extract the document path from the cloud event data."""
    # Try various methods to extract the document path
    
    # Check for binary data content
    if hasattr(cloud_event, 'data') and isinstance(cloud_event.data, bytes):
        # Convert to text and search for path pattern
        text = cloud_event.data.decode('utf-8', errors='ignore')
        match = re.search(r'(projects/[^/]+/databases/[^/]+/documents/users/[a-zA-Z0-9-]+)', text)
        if match:
            return match.group(1)
    
    # Check for dictionary content
    if hasattr(cloud_event, 'data') and isinstance(cloud_event.data, dict):
        # Check for common fields
        if "value" in cloud_event.data and isinstance(cloud_event.data["value"], dict) and "name" in cloud_event.data["value"]:
            return cloud_event.data["value"]["name"]
        elif "name" in cloud_event.data:
            return cloud_event.data["name"]
        else:
            # Look for any field containing '/users/'
            for key, value in cloud_event.data.items():
                if isinstance(value, str) and '/users/' in value:
                    return value
    
    # Check attributes
    if hasattr(cloud_event, 'attributes') and cloud_event.attributes:
        if 'resource' in cloud_event.attributes and '/users/' in cloud_event.attributes['resource']:
            return cloud_event.attributes['resource']
    
    # Last resort: try to find user ID in any string data
    if hasattr(cloud_event, 'data'):
        if isinstance(cloud_event.data, str):
            match = re.search(r'users/([a-zA-Z0-9-]{36})', cloud_event.data)
            if match:
                return f"projects/pepmvp/databases/pep-mvp/documents/users/{match.group(1)}"
        elif isinstance(cloud_event.data, bytes):
            text = cloud_event.data.decode('utf-8', errors='ignore')
            match = re.search(r'users/([a-zA-Z0-9-]{36})', text)
            if match:
                return f"projects/pepmvp/databases/pep-mvp/documents/users/{match.group(1)}"
    
    return None

@functions_framework.cloud_event
def monitor_user_preferences(cloud_event):
    """Entry point for the Cloud Function.
    This function is triggered only when a user's notification_preferences or next_notification_time
    is updated in the Firestore database.
    
    Args:
        cloud_event: The CloudEvent that triggered this function.
    """
    logger.info("User notification preferences change detected")
    
    try:
        # Check if we have data in the cloud_event
        if not hasattr(cloud_event, 'data') or not cloud_event.data:
            logger.error("No data in cloud_event")
            return
        
        # Debug cloud event properties
        logger.info(f"Cloud Event Type: {cloud_event.type if hasattr(cloud_event, 'type') else 'unknown'}")
        logger.info(f"Cloud Event Subject: {cloud_event.subject if hasattr(cloud_event, 'subject') else 'unknown'}")
        logger.info(f"Cloud Event ID: {cloud_event.id if hasattr(cloud_event, 'id') else 'unknown'}")
        
        # Extract document path
        doc_path = extract_document_path(cloud_event)
        if not doc_path:
            logger.error("Could not extract document path from event data")
            return
        
        logger.info(f"Extracted document path: {doc_path}")
        
        # Extract user_id from the path
        if '/users/' in doc_path:
            user_id = doc_path.split('/users/')[1]
            logger.info(f"Extracted user_id: {user_id}")
            
            # Process user notification update
            process_user_notification_update(user_id)
        else:
            logger.error(f"Not a user document path: {doc_path}")
            
    except Exception as e:
        logger.error(f"Error processing user preference change: {str(e)}")
        logger.error(traceback.format_exc())

def process_user_notification_update(user_id):
    """Process a user document update to schedule notifications."""
    logger.info(f"Processing notification update for user ID: {user_id}")
    
    try:
        # Fetch user document from Firestore
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            logger.error(f"User document {user_id} not found")
            return
        
        user_data = user_doc.to_dict()
        logger.info(f"User data retrieved: {user_data.get('name', 'Unknown user')}")
        
        # Check FCM token
        fcm_token = user_data.get('fcm_token')
        if not fcm_token:
            logger.error(f"No FCM token found for user {user_id}")
            return
        
        logger.info(f"Found FCM token: {fcm_token[:10]}...")
        
        # Check if notifications are enabled
        notification_prefs = user_data.get('notification_preferences', {})
        is_enabled = notification_prefs.get('is_enabled', False)
        
        if not is_enabled:
            logger.info(f"Notifications are disabled for user {user_id}")
            # Cancel any scheduled notifications
            cancel_user_notifications(user_id)
            return
        
        # Extract notification parameters using standardized function
        hour = notification_prefs.get('hour')
        minute = notification_prefs.get('minute')
        
        logger.info(f"Notification preferences: hour={hour}, minute={minute}")
        
        if hour is None or minute is None:
            logger.error(f"Invalid notification time: hour={hour}, minute={minute}")
            return
        
        # Determine user's timezone using standardized function
        user_timezone_offset = extract_timezone_offset(user_data)
        logger.info(f"User timezone offset: UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}")
        
        # Convert hour and minute to integers
        try:
            hour = int(hour)
            minute = int(minute)
        except (ValueError, TypeError):
            logger.error(f"Could not convert hour/minute to integers: hour={hour}, minute={minute}")
            return
        
        # Calculate the next notification time in UTC
        now = datetime.now(timezone.utc)
        logger.info(f"Current time (UTC): {now.isoformat()}")
        
        # Calculate next notification time using standardized function
        next_time = calculate_next_notification_time(
            hour=hour,
            minute=minute,
            user_timezone_offset=user_timezone_offset
        )
        
        logger.info(f"Calculated next notification time (UTC): {next_time.isoformat()}")
        
        # Check for manual override
        next_notification_time_override = user_data.get('next_notification_time_manual_override', False)
        existing_next_time = user_data.get('next_notification_time')
        
        if next_notification_time_override and existing_next_time:
            # If there's a manual override, respect it
            try:
                # Convert to datetime with timezone if needed
                if not hasattr(existing_next_time, 'tzinfo') or existing_next_time.tzinfo is None:
                    existing_next_time = existing_next_time.replace(tzinfo=timezone.utc)
                
                # Only use the existing time if it's in the future
                if existing_next_time > now:
                    logger.info(f"Using manual override notification time: {existing_next_time.isoformat()}")
                    next_time = existing_next_time
                else:
                    logger.info("Manual override time is in the past, using calculated time")
            except Exception as e:
                logger.error(f"Error processing manual override time: {str(e)}")
        
        # Cancel any existing scheduled notifications
        cancel_user_notifications(user_id)
        
        # Update user's next notification time
        try:
            logger.info(f"Updating user {user_id} with next_notification_time: {next_time.isoformat()}")
            user_ref.update({
                'next_notification_time': next_time,
                'next_notification_time_utc': next_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                'next_notification_utc_hour': next_time.hour,
                'next_notification_utc_minute': next_time.minute,
                'notification_timezone_offset': user_timezone_offset
            })
        except Exception as update_error:
            logger.error(f"Error updating user's next_notification_time: {str(update_error)}")
            logger.error(traceback.format_exc())
        
        # Schedule the next notification
        try:
            # Determine if this should be a one-time notification
            is_one_time = user_data.get('is_one_time_notification', False)
            force_today = user_data.get('force_today', False)
            
            logger.info(f"Scheduling notification: is_one_time={is_one_time}, force_today={force_today}")
            
            response_data = schedule_notification(
                user_id=user_id,
                scheduled_time=next_time.isoformat(),
                is_one_time=is_one_time,
                force_today=force_today
            )
            
            # Log the response details
            if isinstance(response_data, dict):
                if 'notification_id' in response_data:
                    logger.info(f"Scheduled notification ID: {response_data['notification_id']}")
                if 'scheduled_for' in response_data:
                    logger.info(f"API scheduled time: {response_data['scheduled_for']}")
                if 'task_name' in response_data:
                    logger.info(f"Task name: {response_data['task_name']}")
            
            logger.info(f"Successfully scheduled notification for {user_id} at {next_time.isoformat()} UTC")
            logger.info(f"This will be {hour}:{minute:02d} in the user's local timezone")
            
        except Exception as schedule_error:
            logger.error(f"Error scheduling notification: {str(schedule_error)}")
            logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"Error processing user notification update: {str(e)}")
        logger.error(traceback.format_exc())

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

def cancel_user_notifications(user_id):
    """Cancel all scheduled notifications for a user."""
    logger.info(f"Cancelling existing notifications for user {user_id}")
    
    try:
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
                'updated_at': admin_firestore.SERVER_TIMESTAMP,
                'cancelled_reason': 'User updated notification preferences'
            })
            logger.info(f"Cancelled notification {notif.id}")
            
            # If we have task_name, try to delete the Cloud Task
            if task_name:
                try:
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
    except Exception as e:
        logger.error(f"Error cancelling user notifications: {str(e)}")
        logger.error(traceback.format_exc())
        return 0

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

def schedule_notification(user_id, scheduled_time, is_one_time=False, custom_title=None, custom_body=None, force_today=False):
    """Call the schedule_notification Cloud Function to schedule a notification."""
    logger.info(f"Scheduling notification for user {user_id}: is_one_time={is_one_time}, force_today={force_today}")
    
    # Ensure scheduled_time is a string in ISO format
    if isinstance(scheduled_time, datetime):
        scheduled_time = scheduled_time.isoformat()
    
    payload = {
        'user_id': user_id,
        'scheduled_time': scheduled_time,
        'is_one_time': is_one_time,
        'force_today': force_today
    }
    
    # Add custom content if provided
    if custom_title:
        payload['custom_title'] = custom_title
    
    if custom_body:
        payload['custom_body'] = custom_body
    
    # URL of the schedule_notification Cloud Function
    url = f"https://us-central1-pepmvp.cloudfunctions.net/schedule_notification"
    
    logger.info(f"Calling schedule_notification with payload: {json.dumps(payload)}")
    
    try:
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
                logger.error(f"Could not parse response as JSON: {response.text}")
                return None
        else:
            error_message = f"Failed to schedule notification: HTTP {response.status_code}: {response.text}"
            logger.error(error_message)
            
            # Try to parse the error response
            try:
                error_json = response.json()
                logger.error(f"Error details: {json.dumps(error_json)}")
            except:
                logger.error("Could not parse error response as JSON")
                
            raise Exception(error_message)
    except requests.exceptions.RequestException as req_error:
        error_message = f"Request error when calling schedule_notification: {str(req_error)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        raise Exception(error_message)