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
    - client_correlation_id: string
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
        client_correlation_id = request.args.get('client_correlation_id')

        # Validate required parameters
        if not user_id or not exercise_id or not client_correlation_id:
            return {'error': 'Missing required parameters: user_id, exercise_id, and client_correlation_id'}, 400, headers

        # Initialize Firestore DB
        db = firestore.Client(project='pepmvp', database='pep-mvp')

        # --- Query for analyses using client_correlation_id ---
        analyses_query = (
            db.collection('exercises')
            .document(exercise_id)
            .collection('analyses')
            .where('user_id', '==', user_id)
            .where('client_correlation_id', '==', client_correlation_id)
            .limit(1)
        )

        print(f"Querying for analysis with user_id: {user_id}, exercise_id: {exercise_id}, client_correlation_id: {client_correlation_id}")

        # Execute query
        analyses = analyses_query.stream() # Use stream() for iterator
        doc_list = list(analyses)

        # Check if any document matched the criteria
        if not doc_list:
            message = "Feedback not ready yet. No need to reveal this to the user, just call this tool `get_pose_feedback` again later. Absolutely do not make up feedback to the user, just say nothing and move on to other points you need to cover in the exercise session according to the instructions"
            print(f"ℹ️ {message} for client_correlation_id: {client_correlation_id}")
            return {
                'success': True,
                'hasAnalysis': False,
                'message': message,
                'analysisId': None,
                'clientCorrelationId': client_correlation_id
            }, 200, headers

        # An analysis matching the criteria was found
        doc_snapshot = doc_list[0]
        retrieved_analysis_id = doc_snapshot.id
        latest_analysis = doc_snapshot.to_dict()

        print(f"✅ Found analysis {retrieved_analysis_id} matching client_correlation_id: {client_correlation_id}.")
        # Ensure raw_response is fetched correctly
        feedback_text = latest_analysis.get('raw_response', '')
        if not feedback_text:
             print(f"⚠️ Analysis {retrieved_analysis_id} found, but 'raw_response' field is empty or missing.")
             feedback_text = "Analysis found, but feedback content is missing."

        return {
            'success': True,
            'hasAnalysis': True,
            'feedback': feedback_text,
            'analysisId': retrieved_analysis_id,
            'clientCorrelationId': client_correlation_id
        }, 200, headers

    except Exception as e:
        print(f"❌ Error in get_latest_feedback: {str(e)}")
        # import traceback
        # print(traceback.format_exc())
        return {
            'error': 'Internal server error',
            'message': str(e)
        }, 500, headers
