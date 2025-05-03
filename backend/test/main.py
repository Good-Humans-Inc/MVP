# main.py
import functions_framework
import firebase_admin
from firebase_admin import credentials, messaging
import json
import os

# Initialize Firebase (only once)
try:
    app = firebase_admin.get_app()
except ValueError:
    # Path to service account credentials file (downloaded from Firebase Console)
    # For deployment, use Secret Manager or environment variables
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

@functions_framework.http
def send_test_notification(request):
    """
    Cloud Function to send a test notification via FCM.
    
    Request format:
    {
        "token": "device-fcm-token",  // Required
        "title": "Optional custom title",  // Optional
        "body": "Optional custom message"   // Optional
    }
    """
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        # Get request data
        request_json = request.get_json(silent=True)
        
        if not request_json or 'token' not in request_json:
            return (json.dumps({'error': 'Missing required FCM token'}), 400, headers)
        
        # Extract parameters
        token = request_json.get('token')
        title = request_json.get('title', 'Test Notification')
        body = request_json.get('body', 'This is a test notification from Firebase Cloud Messaging!')
        
        # Define your app's bundle ID for iOS
        bundle_id = "yanffyy.xyz.MVP"  # Replace with your actual bundle ID
        
        # Create message with proper APNS configuration
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={
                'type': 'test_notification',
                'click_action': 'FLUTTER_NOTIFICATION_CLICK',
            },
            token=token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    priority='high',
                    channel_id='test_channel'
                ),
            ),
            apns=messaging.APNSConfig(
                headers={
                    'apns-push-type': 'alert',
                    'apns-priority': '10',
                    'apns-topic': bundle_id
                },
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=title,
                            body=body,
                        ),
                        badge=1,
                        sound='default',
                    ),
                ),
            ),
        )
        
        # Send message
        response = messaging.send(message)
        
        return (json.dumps({
            'success': True,
            'message': 'Notification sent successfully',
            'message_id': response
        }), 200, headers)
        
    except Exception as e:
        return (json.dumps({
            'success': False,
            'error': str(e)
        }), 500, headers)