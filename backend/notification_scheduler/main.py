import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from datetime import datetime, timezone, timedelta
import json
import uuid
import os
from google.cloud import firestore
import requests

try:
    # Initialize Firebase Admin with default credentials
    firebase_admin.initialize_app()
    
    # Initialize Firestore client properly
    db = firestore.client()
    print("✅ Firebase and Firestore initialized successfully")
except Exception as e:
    print(f"❌ Error initializing Firebase: {str(e)}")
    # Continue execution - we'll handle errors in the endpoints

# CORS headers
headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST',
    'Access-Control-Allow-Headers': 'Content-Type',
}

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
    print(f"⏰ Current time (UTC): {now.isoformat()}")
    
    # First, convert the current UTC time to the user's local time
    user_local_time = now.astimezone(timezone(timedelta(hours=user_timezone_offset)))
    print(f"🌐 Current time in user's timezone (UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}): {user_local_time.isoformat()}")
    
    # Create a base date in the user's timezone (today at midnight)
    user_base_date = user_local_time.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Create the target time in user's local timezone
    user_target_time = user_base_date.replace(hour=hour, minute=minute)
    print(f"🎯 Target time in user's timezone: {user_target_time.isoformat()}")
    
    # If target time has passed in user's timezone, add a day
    if user_target_time <= user_local_time:
        user_target_time += timedelta(days=1)
        print(f"⏭️ Target time already passed in user's timezone, scheduling for tomorrow: {user_target_time.isoformat()}")
        
    # Convert the final time back to UTC for storage and scheduling
    target_time_utc = user_target_time.astimezone(timezone.utc)
    print(f"⏰ Final notification time (UTC): {target_time_utc.isoformat()}")
    
    return target_time_utc

def schedule_next_notification(user_id, user_data):
    """Schedule the next notification for the user."""
    try:
        # Get notification preferences
        notification_prefs = user_data.get('notification_preferences', {})
        hour = notification_prefs.get('hour')
        minute = notification_prefs.get('minute')
        
        if hour is None or minute is None:
            print(f"⚠️ Invalid notification time for user {user_id}: hour={hour}, minute={minute}")
            return False
        
        # Get user's timezone offset
        user_timezone_offset = get_user_timezone_offset(user_data)
        print(f"🌐 User timezone offset: UTC{'+' if user_timezone_offset >= 0 else ''}{user_timezone_offset}")
        
        # Calculate next notification time using the standardized function
        next_time = calculate_next_notification_time(
            hour=hour,
            minute=minute,
            user_timezone_offset=user_timezone_offset
        )
        
        # Update the user's next notification time in Firestore
        user_ref = db.collection('users').document(user_id)
        user_ref.update({
            'next_notification_time': next_time
        })
        
        # Call the schedule_notification API
        try:
            notification_data = {
                'user_id': user_id,
                'scheduled_time': next_time.isoformat(),
                'is_one_time': False
            }
            
            response = requests.post(
                'https://us-central1-pepmvp.cloudfunctions.net/schedule_notification',
                json=notification_data,
                timeout=30
            )
            
            if response.status_code == 200:
                print(f"✅ Successfully scheduled next notification for user {user_id}")
                return True
            else:
                print(f"❌ Failed to schedule notification: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error calling schedule_notification API: {str(e)}")
            return False
            
    except Exception as e:
        print(f"❌ Error scheduling next notification: {str(e)}")
        return False

@functions_framework.http
def check_due_notifications(request):
    """Checks for and sends notifications that are due.
    This function is designed to be triggered by Cloud Scheduler every 5 minutes.
    """
    # Enable CORS
    if request.method == 'OPTIONS':
        return ('', 204, headers)
    
    try:
        print("🔍 Starting check for due notifications")
        
        # Get current time in UTC
        now = datetime.now(timezone.utc)
        
        # Look for users with notifications due within the next 5 minutes
        # or overdue by up to 30 minutes (to catch missed notifications)
        start_time = now - timedelta(minutes=30)  # Include notifications we might have missed
        end_time = now + timedelta(minutes=5)     # Include notifications coming up soon
        
        print(f"⏰ Checking for notifications between {start_time.isoformat()} and {end_time.isoformat()}")
        
        # Query users with next_notification_time in our window
        try:
            users_query = db.collection('users').where(
                'next_notification_time', '>=', start_time
            ).where(
                'next_notification_time', '<=', end_time
            ).stream()
        except Exception as e:
            print(f"❌ Error querying users collection: {str(e)}")
            return (json.dumps({
                'status': 'error',
                'message': f"Database query error: {str(e)}"
            }), 500, headers)
        
        processed_count = 0
        sent_count = 0
        error_count = 0
        
        # Process each user with a due notification
        for user_doc in users_query:
            try:
                processed_count += 1
                user_id = user_doc.id
                user_data = user_doc.to_dict()
                
                # Get notification time
                next_notification_time = user_data.get('next_notification_time')
                if not next_notification_time:
                    print(f"⚠️ User {user_id} has no next_notification_time")
                    continue
                
                # Convert to datetime if needed
                if hasattr(next_notification_time, 'timestamp'):
                    next_time_dt = datetime.fromtimestamp(next_notification_time.timestamp(), tz=timezone.utc)
                else:
                    try:
                        next_time_dt = datetime.fromisoformat(str(next_notification_time).replace('Z', '+00:00'))
                    except (ValueError, TypeError) as e:
                        print(f"❌ Error parsing next_notification_time for user {user_id}: {str(e)}")
                        continue
                
                # Get notification preferences
                notification_prefs = user_data.get('notification_preferences', {})
                is_enabled = notification_prefs.get('is_enabled', False)
                
                if not is_enabled:
                    print(f"⚠️ Notifications disabled for user {user_id}")
                    continue
                
                # Check for FCM token
                fcm_token = user_data.get('fcm_token')
                if not fcm_token:
                    print(f"⚠️ No FCM token for user {user_id}")
                    continue
                
                # Get user details
                username = user_data.get('name', 'User')
                
                # Check for recent notifications in the last 15 minutes
                fifteen_mins_ago = now - timedelta(minutes=15)
                try:
                    recent_notifications = db.collection('notifications') \
                        .where('user_id', '==', user_id) \
                        .where('created_at', '>', fifteen_mins_ago) \
                        .limit(1) \
                        .get()
                except Exception as e:
                    print(f"❌ Error checking recent notifications for user {user_id}: {str(e)}")
                    continue
                
                if len(list(recent_notifications)) > 0:
                    print(f"⚠️ User {user_id} already received a notification recently, skipping")
                    continue
                
                print(f"✅ Sending notification to {username} (ID: {user_id})")
                
                # Get notification content
                next_day_data = user_data.get('next_day_notification', {})
                if not next_day_data:
                    notification_content = {
                        'title': f"Time for Exercise, {username}!",
                        'body': "It's time for your daily exercise routine. Let's keep that streak going!"
                    }
                else:
                    notification_content = {
                        'title': next_day_data.get('title', f"Time for Exercise, {username}!"),
                        'body': next_day_data.get('body', "It's time for your daily exercise routine!")
                    }
                
                # Create notification ID
                notification_id = str(uuid.uuid4())
                
                # App bundle ID for APNs
                bundle_id = user_data.get('app_bundle_id', 'com.pepmvp.app')
                device_type = user_data.get('device_type', 'unknown')
                
                # Save notification record
                try:
                    notification_data = {
                        'id': notification_id,
                        'user_id': user_id,
                        'type': 'exercise_reminder',
                        'scheduled_for': next_time_dt,
                        'status': 'scheduled',
                        'created_at': firestore.SERVER_TIMESTAMP,
                        'content': notification_content,
                        'is_one_time': False  # Regular scheduled notification
                    }
                    db.collection('notifications').document(notification_id).set(notification_data)
                except Exception as e:
                    print(f"❌ Error saving notification record for user {user_id}: {str(e)}")
                    continue
                
                # APNS configuration based on device type
                if device_type and device_type.lower() == 'ios':
                    # Enhanced iOS configuration with alert
                    apns_config = messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                alert=messaging.ApsAlert(
                                    title=notification_content['title'],
                                    body=notification_content['body']
                                ),
                                sound='default',
                                badge=1,
                                content_available=True,
                                mutable_content=True,
                                category='EXERCISE_REMINDER'
                            )
                        ),
                        headers={
                            'apns-push-type': 'alert',
                            'apns-priority': '10',  # High priority
                            'apns-topic': bundle_id
                        }
                    )
                else:
                    # Standard configuration for other devices
                    apns_config = messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                sound='default',
                                badge=1,
                                content_available=True,
                                mutable_content=True,
                                category='EXERCISE_REMINDER'
                            )
                        ),
                        headers={
                            'apns-push-type': 'background',
                            'apns-priority': '5',
                            'apns-topic': bundle_id
                        }
                    )
                
                # Compose FCM message
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=notification_content['title'],
                        body=notification_content['body']
                    ),
                    data={
                        'notification_id': notification_id,
                        'user_id': user_id,
                        'type': 'exercise_reminder',
                        'scheduled_time': next_time_dt.isoformat(),
                        'is_one_time': 'false'  # Regular scheduled notification
                    },
                    token=fcm_token,
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            priority='high',
                            channel_id='exercise_reminders'
                        )
                    ),
                    apns=apns_config
                )
                
                # Send notification
                try:
                    response = messaging.send(message)
                    sent_count += 1
                    print(f"✅ Notification sent to {username}: {response}")
                    
                    # Update notification status
                    try:
                        db.collection('notifications').document(notification_id).update({
                            'status': 'sent',
                            'sent_at': firestore.SERVER_TIMESTAMP,
                            'message_id': response
                        })
                    except Exception as e:
                        print(f"❌ Error updating notification status for {notification_id}: {str(e)}")
                    
                    # Schedule next notification based on preferences
                    if notification_prefs.get('frequency') == 'daily':
                        hour = notification_prefs.get('hour')
                        minute = notification_prefs.get('minute')
                        if hour is not None and minute is not None:
                            # Calculate next day at the same hour/minute
                            tomorrow = now + timedelta(days=1)
                            next_notification = tomorrow.replace(
                                hour=hour, 
                                minute=minute, 
                                second=0, 
                                microsecond=0
                            )
                            
                            try:
                                user_ref = db.collection('users').document(user_id)
                                user_ref.update({
                                    'next_notification_time': next_notification
                                })
                                print(f"⏰ Scheduled next notification for user {user_id}: {next_notification.isoformat()}")
                            except Exception as e:
                                print(f"❌ Error scheduling next notification for user {user_id}: {str(e)}")
                    
                except messaging.ApiCallError as fcm_error:
                    error_count += 1
                    error_msg = str(fcm_error)
                    print(f"❌ FCM API Error for user {user_id}: {error_msg}")
                    
                    if 'registration-token-not-registered' in error_msg.lower():
                        try:
                            user_ref = db.collection('users').document(user_id)
                            user_ref.update({
                                'fcm_token': firestore.DELETE_FIELD,
                                'notification_status': 'token_expired'
                            })
                        except Exception as e:
                            print(f"❌ Error updating user token status for {user_id}: {str(e)}")
                    
                    try:
                        db.collection('notifications').document(notification_id).update({
                            'status': 'failed',
                            'error': error_msg
                        })
                    except Exception as e:
                        print(f"❌ Error updating notification failure status for {notification_id}: {str(e)}")
            
            except Exception as user_error:
                error_count += 1
                print(f"❌ Error processing user {user_doc.id}: {str(user_error)}")
        
        print(f"📊 Summary: Processed {processed_count} users, sent {sent_count} notifications, encountered {error_count} errors")
        
        return (json.dumps({
            'status': 'success',
            'processed': processed_count,
            'sent': sent_count,
            'errors': error_count
        }), 200, headers)
    
    except Exception as e:
        print(f"❌ GENERAL ERROR: {str(e)}")
        import traceback
        print(f"📋 Stack trace: {traceback.format_exc()}")
        
        return (json.dumps({
            'status': 'error',
            'message': str(e)
        }), 500, headers)