import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# Initialize Firebase
firebase_admin.initialize_app()

# Connect to Firestore
db = firestore.client()

# Update the user's next_notification_time field
doc_ref = db.collection('users').document('9b11420d-be73-49fd-af1d-bff1ed4f66a0')
doc_ref.update({
    'next_notification_time': datetime.datetime.utcnow().isoformat() + 'Z'
})

print("✅ Firestore document updated!")
