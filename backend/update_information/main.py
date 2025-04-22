import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import json
import uuid
from google.cloud import secretmanager

# Initialize Firebase Admin with default credentials
firebase_admin.initialize_app()
db = firestore.Client(project='pepmvp', database='pep-mvp')

def get_secret(secret_id):
    """Get secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/pepmvp/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

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
        
        # Get update data
        notification_time = request_json.get('notification_time')
        ultimate_goal = request_json.get('ultimate_goal')
        exercise_routine = request_json.get('exercise_routine')
        
        # Prepare update data
        update_data = {}
        
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
                        'updated_by': 'elevenlabs_agent'
                    }
                else:
                    return (json.dumps({'error': 'Invalid notification time format'}), 400, headers)
            except (ValueError, AttributeError):
                return (json.dumps({'error': 'Invalid notification time format'}), 400, headers)
        
        # Update ultimate goal if provided
        if ultimate_goal:
            update_data['ultimate_goal'] = ultimate_goal
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
        if 'notification_preferences' in update_data:
            # Get user's FCM token
            user_data = user_doc.to_dict()
            fcm_token = user_data.get('fcm_token')
            
            if fcm_token:
                # Get the user's original notification time from onboarding
                user_data = user_doc.to_dict()
                original_schedule = user_data.get('notification_schedule', {})
                original_hour = original_schedule.get('hour', 9)  # Default to 9 AM if not set
                original_minute = original_schedule.get('minute', 0)  # Default to 0 if not set
                
                # Create a scheduled time for tomorrow using the new time from the update
                now = datetime.now()
                tomorrow_scheduled_time = now.replace(
                    hour=update_data['notification_preferences']['hour'],
                    minute=update_data['notification_preferences']['minute'],
                    second=0,
                    microsecond=0
                )
                
                # If the time has already passed today, schedule for tomorrow
                if tomorrow_scheduled_time < now:
                    tomorrow_scheduled_time = tomorrow_scheduled_time + timedelta(days=1)
                
                # Format for ISO 8601
                tomorrow_scheduled_time_str = tomorrow_scheduled_time.isoformat() + 'Z'
                
                # Call the schedule_notification function for tomorrow only
                try:
                    from schedule_notification.main import schedule_notification
                    
                    # Create a mock request object
                    class MockRequest:
                        def __init__(self, json_data):
                            self.json_data = json_data
                        
                        def get_json(self):
                            return self.json_data
                    
                    # Create notification request for tomorrow only
                    notification_request = MockRequest({
                        'user_id': user_id,
                        'scheduled_time': tomorrow_scheduled_time_str,
                        'is_one_time': True  # Flag to indicate this is a one-time notification
                    })
                    
                    # Call the function
                    schedule_notification(notification_request)
                    
                    # Update user's next notification time
                    user_ref.update({
                        'notification_schedule.next_notification': tomorrow_scheduled_time,
                        'notification_schedule.temporary_override': {
                            'hour': update_data['notification_preferences']['hour'],
                            'minute': update_data['notification_preferences']['minute'],
                            'until': (tomorrow_scheduled_time + timedelta(days=1)).isoformat() + 'Z'
                        }
                    })
                    
                except Exception as e:
                    print(f"Error scheduling notification: {str(e)}")
        
        return (json.dumps({
            'status': 'success',
            'message': 'User information updated successfully',
            'updated_fields': list(update_data.keys())
        }), 200, headers)
            
    except Exception as e:
        print(f"Error updating user information: {str(e)}")
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