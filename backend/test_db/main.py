# monitor_notification_changes.py
import functions_framework
from firebase_admin import firestore, initialize_app, messaging
import json
import uuid

initialize_app()
db = firestore.client()

@functions_framework.cloud_event
def monitor_notification_changes(cloud_event):
    print("🔔 Firestore change detected")

    data = cloud_event.data
    path = data["value"]["name"]
    if "/users/" not in path:
        return

    user_id = path.split("/users/")[1]
    doc = db.collection("users").document(user_id).get()

    if not doc.exists:
        print(f"User {user_id} not found.")
        return

    user_data = doc.to_dict()
    fcm_token = user_data.get("fcm_token")
    if not fcm_token:
        print(f"No FCM token for user {user_id}")
        return

    notification = messaging.Message(
        notification=messaging.Notification(
            title="Time to exercise!",
            body="Let's stick to your PT goals today!"
        ),
        token=fcm_token
    )

    response = messaging.send(notification)
    print(f"✅ Notification sent: {response}")
