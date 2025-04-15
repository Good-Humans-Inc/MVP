import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
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
        patient_id = request_json.get('patient_id')
        
        if not patient_id:
            return (json.dumps({'error': 'Missing patient_id'}), 400, headers)
        
        # Check if patient exists
        patient_ref = db.collection('patients').document(patient_id)
        patient_doc = patient_ref.get()
        
        if not patient_doc.exists:
            return (json.dumps({'error': 'Patient not found'}), 404, headers)
        
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
        
        # Update patient document
        patient_ref.update(update_data)
        
        # Create an activity log entry
        activity_id = str(uuid.uuid4())
        activity_data = {
            'id': activity_id,
            'patient_id': patient_id,
            'type': 'profile_update',
            'updated_fields': list(update_data.keys()),
            'updated_at': firestore.SERVER_TIMESTAMP,
            'updated_by': 'elevenlabs_agent'
        }
        
        db.collection('activities').document(activity_id).set(activity_data)
        
        # If notification time was updated, schedule a notification
        if 'notification_preferences' in update_data:
            # Get patient's FCM token
            patient_data = patient_doc.to_dict()
            fcm_token = patient_data.get('fcm_token')
            
            if fcm_token:
                # Create a scheduled time for tomorrow at the specified hour and minute
                now = datetime.now()
                scheduled_time = now.replace(
                    hour=update_data['notification_preferences']['hour'],
                    minute=update_data['notification_preferences']['minute'],
                    second=0,
                    microsecond=0
                )
                
                # If the time has already passed today, schedule for tomorrow
                if scheduled_time < now:
                    scheduled_time = scheduled_time.replace(day=now.day + 1)
                
                # Format for ISO 8601
                scheduled_time_str = scheduled_time.isoformat() + 'Z'
                
                # Call the schedule_notification function
                try:
                    from schedule_notification.main import schedule_notification
                    
                    # Create a mock request object
                    class MockRequest:
                        def __init__(self, json_data):
                            self.json_data = json_data
                        
                        def get_json(self):
                            return self.json_data
                    
                    # Create notification request
                    notification_request = MockRequest({
                        'patient_id': patient_id,
                        'notification_type': 'exercise_reminder',
                        'scheduled_time': scheduled_time_str
                    })
                    
                    # Call the function
                    schedule_notification(notification_request)
                except Exception as e:
                    print(f"Error scheduling notification: {str(e)}")
        
        return (json.dumps({
            'status': 'success',
            'message': 'Patient information updated successfully',
            'updated_fields': list(update_data.keys())
        }), 200, headers)
            
    except Exception as e:
        print(f"Error updating patient information: {str(e)}")
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