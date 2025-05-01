# update_timezone/main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
import json
import datetime

# Initialize Firebase Admin if not already initialized
try:
    app = firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()

db = firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.http
def update_timezone(request):
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
        timezone_offset = request_json.get('timezone')
        
        # Validate required fields
        if not user_id:
            return (json.dumps({'error': 'Missing user_id'}), 400, headers)
        
        if timezone_offset is None:
            return (json.dumps({'error': 'Missing timezone offset'}), 400, headers)
        
        # Try to parse timezone as float
        try:
            timezone_offset_float = float(timezone_offset)
        except (ValueError, TypeError):
            return (json.dumps({'error': 'Invalid timezone format. Expected hours offset (e.g., -7, 5.5)'}), 400, headers)
        
        # Check if user exists
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return (json.dumps({'error': 'User not found'}), 404, headers)
        
        # Get current user data
        user_data = user_doc.to_dict()
        current_timezone = user_data.get('timezone')
        
        # Check if timezone has changed
        if current_timezone is not None and float(current_timezone) == timezone_offset_float:
            # No change needed
            return (json.dumps({
                'status': 'unchanged',
                'message': 'Timezone is already up to date',
                'timezone': timezone_offset
            }), 200, headers)
        
        # Update timezone in user document
        update_data = {
            'timezone': str(timezone_offset_float),
            'timezone_updated_at': firestore.SERVER_TIMESTAMP
        }
        
        # Check if notification preferences exist and need to be updated
        notification_prefs = user_data.get('notification_preferences')
        if notification_prefs and isinstance(notification_prefs, dict):
            if 'hour_local' in notification_prefs and 'minute_local' in notification_prefs:
                # Keep the original local hour/minute but update UTC values based on new timezone
                local_hour = notification_prefs.get('hour_local')
                local_minute = notification_prefs.get('minute_local')
                
                # Calculate the next notification time
                now = datetime.datetime.now(datetime.timezone.utc)
                user_tz = datetime.timezone(datetime.timedelta(hours=timezone_offset_float))
                now_user_tz = now.astimezone(user_tz)
                
                # Create a datetime with the notification time in user's timezone
                notification_time_local = now_user_tz.replace(
                    hour=local_hour,
                    minute=local_minute,
                    second=0,
                    microsecond=0
                )
                
                # If target time has already passed today, schedule for tomorrow
                if notification_time_local <= now_user_tz:
                    notification_time_local = notification_time_local + datetime.timedelta(days=1)
                
                # Convert back to UTC for storage
                notification_time_utc = notification_time_local.astimezone(datetime.timezone.utc)
                
                # Store as UTC datetime without timezone info for consistent Firestore storage
                next_notification_time = datetime.datetime(
                    notification_time_utc.year,
                    notification_time_utc.month,
                    notification_time_utc.day,
                    notification_time_utc.hour,
                    notification_time_utc.minute,
                    notification_time_utc.second,
                    notification_time_utc.microsecond
                )
                
                update_data['next_notification_time'] = next_notification_time
                
                print(f"Updated next notification time to {next_notification_time.isoformat()}Z based on local time {local_hour}:{local_minute} in timezone UTC{'+' if timezone_offset_float >= 0 else ''}{timezone_offset_float}")
                print(f"This UTC time is equivalent to {local_hour:02d}:{local_minute:02d} in the user's local timezone")
                
                # Update notification preferences with new UTC values
                update_data['notification_preferences'] = {
                    **notification_prefs,  # Keep all existing fields
                    'hour_utc': notification_time_utc.hour,
                    'minute_utc': notification_time_utc.minute,
                    'timezone_offset': timezone_offset_float,
                    'timezone_updated_at': firestore.SERVER_TIMESTAMP
                }
        
        # Update the user document
        user_ref.update(update_data)
        
        # Log the update
        print(f"Updated timezone for user {user_id} from {current_timezone} to {timezone_offset_float}")
        
        return (json.dumps({
            'status': 'success',
            'message': 'Timezone updated successfully',
            'old_timezone': current_timezone,
            'new_timezone': timezone_offset,
            'utc_hour': update_data.get('notification_preferences', {}).get('hour_utc') if 'notification_preferences' in update_data else None,
            'utc_minute': update_data.get('notification_preferences', {}).get('minute_utc') if 'notification_preferences' in update_data else None
        }), 200, headers)
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error updating timezone: {str(e)}\n{error_details}")
        return (json.dumps({'error': str(e)}), 500, headers) 