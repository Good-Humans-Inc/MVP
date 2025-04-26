import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred)

db = firestore.client()
doc_ref = db.collection("users").document("9b11420d-be73-49fd-af1d-bff1ed4f66a0")
doc_ref.update({
    "next_notification_time": datetime.now(timezone.utc)
})

print("✅ Firestore document updated.")