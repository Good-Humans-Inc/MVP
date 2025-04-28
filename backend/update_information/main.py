# update_information/main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone
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
        
        # Get update data
        notification_time = request_json.get('notification_time')
        ultimate_goal = request_json.get('ultimate_goal')
        exercise_routine = request_json.get('exercise_routine')
        
        # Prepare update data
        update_data = {}
        notification_updated = False
        
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
                    notification_updated = True
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
        scheduled_task_id = None
        
        if notification_updated:
            # Calculate the next notification time
            now = datetime.now(timezone.utc)
            next_time = now.replace(
                hour=update_data['notification_preferences']['hour'], 
                minute=update_data['notification_preferences']['minute'],
                second=0,
                microsecond=0
            )
            
            # If the time has already passed today, schedule for tomorrow
            if next_time <= now:
                next_time = next_time + timedelta(days=1)
            
            # Update the user's next_notification_time
            user_ref.update({
                'next_notification_time': next_time
            })
            
            # Cancel any existing scheduled notifications
            try:
                cancel_existing_scheduled_notifications(user_id)
            except Exception as e:
                print(f"Error cancelling existing notifications: {str(e)}")
            
            # Schedule the next notification
            try:
                task_response = schedule_notification_task(
                    user_id,
                    next_time.isoformat(),
                    is_one_time=False
                )
                if task_response and 'notification_id' in task_response:
                    scheduled_task_id = task_response['notification_id']
            except Exception as e:
                print(f"Error scheduling new notification: {str(e)}")
        
        response_data = {
            'status': 'success',
            'message': 'User information updated successfully',
            'updated_fields': list(update_data.keys())
        }
        
        if scheduled_task_id:
            response_data['scheduled_notification_id'] = scheduled_task_id
            
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

def schedule_notification_task(user_id, scheduled_time, is_one_time=False, custom_title=None, custom_body=None):
    """Call the schedule_notification Cloud Function."""
    # Get the GCP project ID
    project_id = 'pepmvp'  # Your GCP project ID
    
    # Prepare the request payload
    payload = {
        'user_id': user_id,
        'scheduled_time': scheduled_time,
        'is_one_time': is_one_time
    }
    
    if custom_title:
        payload['custom_title'] = custom_title
    
    if custom_body:
        payload['custom_body'] = custom_body
    
    # URL of the schedule_notification Cloud Function
    url = f"https://us-central1-{project_id}.cloudfunctions.net/schedule_notification"
    
    # Make the HTTP request
    response = requests.post(url, json=payload)
    
    # Process the response
    if response.status_code == 200:
        return response.json()
    else:
        error_message = f"Failed to schedule notification: {response.text}"
        print(error_message)
        raise Exception(error_message)

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