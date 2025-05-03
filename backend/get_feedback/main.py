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

        # --- Get the timestamp of the last analysis request ---
        since_dt = None
        try:
            status_doc_ref = db.collection('user_analysis_status').document(user_id)
            status_doc = status_doc_ref.get()
            if status_doc.exists:
                status_data = status_doc.to_dict()
                since_dt = status_data.get('last_request_timestamp')
                if since_dt:
                     # Firestore timestamp objects are already timezone-aware (UTC)
                     print(f"Retrieved last_request_timestamp for user {user_id}: {since_dt.isoformat()}")
                else:
                     print(f"⚠️ last_request_timestamp field not found in status doc for user {user_id}.")
            else:
                print(f"ℹ️ No analysis status document found for user {user_id}. Will fetch latest overall.")
        except Exception as e_status_read:
            print(f"⚠️ Error reading status doc for user {user_id}: {e_status_read}. Will fetch latest overall.")


        # --- Query for analyses ---
        analyses_query = (db
            .collection('exercises')
            .document(exercise_id)
            .collection('analyses')
            .where('user_id', '==', user_id))

        # Add timestamp filter *only if* we successfully retrieved a timestamp
        if since_dt:
            analyses_query = analyses_query.where('timestamp', '>', since_dt)
        else:
             # If no timestamp, we log it but still proceed to get the absolute latest
             print(f"Proceeding without time filter for user {user_id}, exercise {exercise_id}.")


        # Order by timestamp descending and limit to 1
        analyses_query = analyses_query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1)

        # Execute query
        analyses = analyses_query.get()
        doc_list = list(analyses)

        # Check if any document matched the criteria
        if not doc_list:
            message = "Feedback not ready yet. Try calling this tool again later."
            # Adjusted message formatting
            if since_dt:
                message += f" Feedback should be since ({since_dt.isoformat()})."
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
        return {
            'success': True,
            'hasAnalysis': True,
            'feedback': latest_analysis.get('raw_response', ''),
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
