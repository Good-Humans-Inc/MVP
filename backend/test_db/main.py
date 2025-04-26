# monitor_user_changes.py
from firebase_functions import firestore_fn
from firebase_admin import initialize_app

# Initialize Firebase Admin SDK
app = initialize_app()

@firestore_fn.on_document_written(document="users/{userId}")
def monitor_user_changes(data, context):
    print("🚀 Firestore event received!")
    print("Data:", data)
    print("Context:", context)
