# update_notification_time.py
import functions_framework
from firebase_admin import firestore, initialize_app
from flask import jsonify, request
from datetime import datetime, timezone

initialize_app()

@functions_framework.http
def update_notification_time(request):
    data = request.get_json()
    user_id = data.get("user_id")
    timestamp = data.get("next_notification_time")  # ISO string or None

    if not user_id or not timestamp:
        return jsonify({"error": "Missing user_id or timestamp"}), 400

    db = firestore.client()
    doc_ref = db.collection("users").document(user_id)
    doc_ref.update({
        "next_notification_time": datetime.fromisoformat(timestamp).astimezone(timezone.utc)
    })

    return jsonify({"status": "success"}), 200
