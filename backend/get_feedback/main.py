import functions_framework
from firebase_admin import initialize_app, firestore
import firebase_admin
from datetime import datetime, timezone

# Initialize Firebase Admin
try:
    initialize_app()
except ValueError:
    # App already initialized
    pass

@functions_framework.http
def get_latest_feedback(request):
    """
    HTTP Cloud Function to get the latest feedback relevant to the most recent analysis request.
    Expects a GET request with query parameters:
    - user_id: string
    - exercise_id: string
    """
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    try:
        # Get parameters from query string
        user_id = request.args.get('user_id')
        exercise_id = request.args.get('exercise_id')

        # Validate required parameters
        if not user_id or not exercise_id:
            return {'error': 'Missing required parameters: user_id and exercise_id'}, 400, headers

        # Initialize Firestore DB
        db = firestore.Client(project='pepmvp', database='pep-mvp')

        # --- Get the timestamp of the last analysis request from the USER document ---
        since_dt = None
        try:
            # user_status_doc_ref = db.collection('user_analysis_status').document(user_id)
            user_doc_ref = db.collection('users').document(user_id) # <-- Change collection to 'users'
            user_doc = user_doc_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                # since_dt = status_data.get('last_request_timestamp')
                since_dt = user_data.get('last_analysis_request_timestamp') # <-- Change field name
                if since_dt:
                     # Firestore timestamp objects are already timezone-aware (UTC)
                     print(f"Retrieved last_analysis_request_timestamp for user {user_id}: {since_dt.isoformat()}")
                else:
                     print(f"⚠️ last_analysis_request_timestamp field not found in user doc for user {user_id}.")
            else:
                # This case should be rare if user exists, but handle it
                print(f"ℹ️ User document not found for user {user_id}. Cannot get timestamp.")
        except Exception as e_status_read:
            # Renamed error variable for clarity
            print(f"⚠️ Error reading user doc for user {user_id} to get timestamp: {e_status_read}. Will fetch latest overall.")

        # --- Query for analyses ---
        analyses_query = (db
            .collection('exercises')
            .document(exercise_id)
            .collection('analyses')
            .where('user_id', '==', user_id))

        # Add timestamp filter *only if* we successfully retrieved a timestamp
        if since_dt:
            analyses_query = analyses_query.where('timestamp', '>', since_dt)
            print(f"Applying time filter: timestamp > {since_dt.isoformat()}")
        else:
             # If no timestamp, we log it but still proceed to get the absolute latest
             print(f"Proceeding without time filter for user {user_id}, exercise {exercise_id}.")

        # Order by timestamp descending and limit to 1
        analyses_query = analyses_query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1)

        # Execute query
        analyses = analyses_query.stream() # Use stream() for iterator
        doc_list = list(analyses)

        # Check if any document matched the criteria
        if not doc_list:
            message = "Feedback not ready yet. No need to reveal this to the user, just call this tool `get_pose_feedback` again later. Absolutely do not make up feedback to the user, just say nothing and move on to other points you need to cover in the exercise session according to the instructions"
            print(f"ℹ️ {message}")
            return {
                'success': True,
                'hasAnalysis': False,
                'message': message,
                'analysisId': None
            }, 200, headers

        # An analysis matching the criteria was found
        doc_snapshot = doc_list[0]
        retrieved_analysis_id = doc_snapshot.id
        latest_analysis = doc_snapshot.to_dict()

        print(f"✅ Found analysis {retrieved_analysis_id} matching criteria.")
        # Ensure raw_response is fetched correctly
        feedback_text = latest_analysis.get('raw_response', '')
        if not feedback_text:
             print(f"⚠️ Analysis {retrieved_analysis_id} found, but 'raw_response' field is empty or missing.")
             feedback_text = "Analysis found, but feedback content is missing."

        return {
            'success': True,
            'hasAnalysis': True,
            'feedback': feedback_text,
            'analysisId': retrieved_analysis_id
        }, 200, headers

    except Exception as e:
        print(f"❌ Error in get_latest_feedback: {str(e)}")
        # import traceback
        # print(traceback.format_exc())
        return {
            'error': 'Internal server error',
            'message': str(e)
        }, 500, headers
