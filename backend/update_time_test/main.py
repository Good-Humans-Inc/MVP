import functions_framework
from firebase_admin import firestore, initialize_app

# Initialize Firestore once
initialize_app()
db = firestore.client()

@functions_framework.http
def update_user_name(request):
    """HTTP POST to update user name."""
    request_json = request.get_json(silent=True)
    
    user_id = request_json.get('user_id')
    new_name = request_json.get('new_name')
    
    if not user_id or not new_name:
        return "Missing user_id or new_name.", 400
    
    user_ref = db.collection('users').document(user_id)
    user_ref.update({'name': new_name})
    
    print(f"✅ Updated name for user {user_id} to {new_name}")
    return "Name updated successfully.", 200
