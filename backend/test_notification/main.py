import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from firebase_functions import https_fn
import json
from datetime import datetime, timezone, timedelta
import requests
import logging

# Initialize Firebase Admin if not already initialized
try:
    app = firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()

@https_fn.on_call()
def send_test_notification(req: https_fn.CallableRequest) -> dict:
    """
    Callable function to send a test FCM notification to a device
    
    Expected request data:
    {
        "token": "FCM device token",
        "title": "Notification title",
        "body": "Notification body"
    }
    """
    try:
        # Get data from request
        data = req.data
        
        if not data.get("token"):
            return {"success": False, "error": "Missing device token"}
        
        # Log the test attempt
        print(f"Attempting to send test notification to token: {data.get('token')[:10]}...")
        
        # Create message with improved APNS configuration for iOS
        message = messaging.Message(
            notification=messaging.Notification(
                title=data.get("title", "Test Notification"),
                body=data.get("body", "This is a test notification from Firebase")
            ),
            token=data.get("token"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=data.get("title", "Test Notification"),
                            body=data.get("body", "This is a test notification from Firebase")
                        ),
                        badge=1,
                        sound="default"
                    )
                ),
                headers={
                    'apns-push-type': 'alert',
                    'apns-priority': '10'
                }
            )
        )
        
        # Send message
        response = messaging.send(message)
        print(f"Test notification sent successfully: {response}")
        return {"success": True, "message_id": response}
        
    except Exception as e:
        error_message = str(e)
        print(f"Error sending test notification: {error_message}")
        return {"success": False, "error": error_message}