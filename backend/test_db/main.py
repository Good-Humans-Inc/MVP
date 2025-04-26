from firebase_admin import initialize_app

# Initialize Firebase Admin SDK
app = initialize_app()

def monitor_user_changes(data, context):
    print("🚀 Firestore event received!")
    print("Data:", data)
    print("Context:", context)

