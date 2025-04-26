import firebase_admin
from firebase_admin import credentials, firestore
import datetime

cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred)

db = firestore.client()

doc_ref = db.collection('users').document('9b11420d-be73-49fd-af1d-bff1ed4f66a0')
doc_ref.update({
    'next_notification_time': datetime.datetime.now(datetime.timezone.utc)
})

print("✅ Firestore document updated with proper event trigger!")
