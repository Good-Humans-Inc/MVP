import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime, timedelta
import json
import uuid
from google.cloud import secretmanager
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds

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
def schedule_notification(request):
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
        notification_type = request_json.get('notification_type', 'exercise_reminder')
        scheduled_time = request_json.get('scheduled_time')
        exercise_id = request_json.get('exercise_id')
        
        if not patient_id:
            return (json.dumps({'error': 'Missing patient_id'}), 400, headers)
        
        # Get patient's FCM token
        patient_ref = db.collection('patients').document(patient_id)
        patient_doc = patient_ref.get()
        
        if not patient_doc.exists:
            return (json.dumps({'error': 'Patient not found'}), 404, headers)
        
        patient_data = patient_doc.to_dict()
        fcm_token = patient_data.get('fcm_token')
        
        if not fcm_token:
            return (json.dumps({'error': 'Patient has no FCM token'}), 400, headers)
        
        # Parse scheduled time
        try:
            scheduled_datetime = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return (json.dumps({'error': 'Invalid scheduled_time format'}), 400, headers)
        
        # Create notification ID
        notification_id = str(uuid.uuid4())
        
        # Create notification document
        notification_data = {
            'id': notification_id,
            'patient_id': patient_id,
            'type': notification_type,
            'scheduled_for': scheduled_datetime,
            'status': 'scheduled',
            'created_at': firestore.SERVER_TIMESTAMP,
            'exercise_id': exercise_id
        }
        
        # Add to Firestore
        db.collection('notifications').document(notification_id).set(notification_data)
        
        # Schedule the notification
        if notification_type == 'exercise_reminder':
            # Get exercise details if exercise_id is provided
            exercise_data = {}
            if exercise_id:
                exercise_ref = db.collection('exercises').document(exercise_id)
                exercise_doc = exercise_ref.get()
                if exercise_doc.exists:
                    exercise_data = exercise_doc.to_dict()
            
            # Create notification content
            title = "Time for your PT exercises!"
            body = "Don't forget to complete your physical therapy exercises today."
            
            # If we have exercise data, personalize the message
            if exercise_data:
                exercise_name = exercise_data.get('name', '')
                if exercise_name:
                    title = f"Time for your {exercise_name} exercise!"
                    body = f"Don't forget to complete your {exercise_name} exercise today."
            
            # Create message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data={
                    'notification_id': notification_id,
                    'patient_id': patient_id,
                    'type': notification_type,
                    'exercise_id': exercise_id or ''
                },
                token=fcm_token,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        priority='high',
                        channel_id='exercise_reminders'
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                            badge=1
                        )
                    )
                )
            )
            
            # Schedule the message
            response = messaging.send(message)
            
            # Update notification status
            db.collection('notifications').document(notification_id).update({
                'status': 'sent',
                'sent_at': firestore.SERVER_TIMESTAMP,
                'message_id': response
            })
            
            return (json.dumps({
                'status': 'success',
                'notification_id': notification_id,
                'message_id': response
            }), 200, headers)
        else:
            return (json.dumps({'error': 'Unsupported notification type'}), 400, headers)
            
    except Exception as e:
        print(f"Error scheduling notification: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

@functions_framework.http
def update_fcm_token(request):
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
        fcm_token = request_json.get('fcm_token')
        
        if not patient_id or not fcm_token:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Update patient's FCM token
        patient_ref = db.collection('patients').document(patient_id)
        patient_ref.update({
            'fcm_token': fcm_token,
            'last_token_update': firestore.SERVER_TIMESTAMP
        })
        
        return (json.dumps({'status': 'success'}), 200, headers)
            
    except Exception as e:
        print(f"Error updating FCM token: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

@functions_framework.http
def send_exercise_notification(request):
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
        exercise_id = request_json.get('exercise_id')
        
        if not patient_id or not exercise_id:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get patient's FCM token
        patient_ref = db.collection('patients').document(patient_id)
        patient_doc = patient_ref.get()
        
        if not patient_doc.exists:
            return (json.dumps({'error': 'Patient not found'}), 404, headers)
        
        patient_data = patient_doc.to_dict()
        fcm_token = patient_data.get('fcm_token')
        
        if not fcm_token:
            return (json.dumps({'error': 'Patient has no FCM token'}), 400, headers)
        
        # Get exercise details
        exercise_ref = db.collection('exercises').document(exercise_id)
        exercise_doc = exercise_ref.get()
        
        if not exercise_doc.exists:
            return (json.dumps({'error': 'Exercise not found'}), 404, headers)
        
        exercise_data = exercise_doc.to_dict()
        
        # Create notification ID
        notification_id = str(uuid.uuid4())
        
        # Create notification content
        title = f"Time for your {exercise_data.get('name', 'PT')} exercise!"
        body = f"Don't forget to complete your {exercise_data.get('name', 'physical therapy')} exercise today."
        
        # Create message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data={
                'notification_id': notification_id,
                'patient_id': patient_id,
                'type': 'exercise_reminder',
                'exercise_id': exercise_id
            },
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    priority='high',
                    channel_id='exercise_reminders'
                )
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1
                    )
                )
            )
        )
        
        # Send the message
        response = messaging.send(message)
        
        # Create notification document
        notification_data = {
            'id': notification_id,
            'patient_id': patient_id,
            'type': 'exercise_reminder',
            'scheduled_for': firestore.SERVER_TIMESTAMP,
            'sent_at': firestore.SERVER_TIMESTAMP,
            'status': 'sent',
            'created_at': firestore.SERVER_TIMESTAMP,
            'exercise_id': exercise_id,
            'message_id': response
        }
        
        # Add to Firestore
        db.collection('notifications').document(notification_id).set(notification_data)
        
        return (json.dumps({
            'status': 'success',
            'notification_id': notification_id,
            'message_id': response
        }), 200, headers)
            
    except Exception as e:
        print(f"Error sending exercise notification: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

# Helper function to serialize Firestore data for JSON
def serialize_firestore_data(data):
    """Helper function to serialize Firestore data for JSON."""
    if isinstance(data, dict):
        return {k: serialize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_firestore_data(item) for item in data]
    elif isinstance(data, DatetimeWithNanoseconds):
        return data.isoformat()
    elif hasattr(data, 'datetime'):  # Handle Firestore Timestamp
        return data.datetime.isoformat()
    else:
        return data 