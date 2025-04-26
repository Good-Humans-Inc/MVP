# monitor_user_changes.py
from firebase_functions import firestore_fn
from firebase_admin import initialize_app

# Initialize Firebase Admin SDK
app = initialize_app()

@firestore_fn.on_document_updated(document="users/{userId}")
def monitor_user_changes(event: firestore_fn.Event[dict]) -> None:
    """Triggered when a user's Firestore document is updated."""
    old_data = event.data.before
    new_data = event.data.after

    old_name = old_data.get('name')
    new_name = new_data.get('name')

    if old_name != new_name:
        print(f"🚨 NAME CHANGED from '{old_name}' to '{new_name}'")
    else:
        print("ℹ️ No name change detected.")
