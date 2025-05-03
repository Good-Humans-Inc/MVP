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
    HTTP Cloud Function to get the latest feedback created after a specific time.
    Expects a GET request with query parameters:
    - user_id: string
    - exercise_id: string
    - since_timestamp: string (Optional, ISO 8601 format UTC e.g., 2023-10-27T10:00:00Z)
                       If provided, only returns analyses created after this time.
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
        since_timestamp_str = request.args.get('since_timestamp') # Optional timestamp

        # Validate required parameters
        if not user_id or not exercise_id:
            return {
                'error': 'Missing required parameters: user_id and exercise_id'
            }, 400, headers

        # Parse the optional timestamp string
        since_dt = None
        if since_timestamp_str:
            try:
                # Attempt to parse various ISO 8601 formats, assuming UTC if no offset
                if since_timestamp_str.endswith('Z'):
                    since_dt = datetime.fromisoformat(since_timestamp_str.replace('Z', '+00:00'))
                else:
                    # Try parsing directly, might need adjustment based on exact format sent
                    since_dt = datetime.fromisoformat(since_timestamp_str)
                    # Ensure it's timezone-aware (assume UTC if naive)
                    if since_dt.tzinfo is None:
                         since_dt = since_dt.replace(tzinfo=timezone.utc)
                print(f"Parsed since_timestamp: {since_dt.isoformat()}")
            except ValueError:
                return {
                    'error': f'Invalid since_timestamp format. Use ISO 8601 UTC (e.g., 2023-10-27T10:00:00Z). Received: {since_timestamp_str}'
                }, 400, headers

        # Initialize Firestore DB
        db = firestore.Client(project='pepmvp', database='pep-mvp')

        # Base query
        analyses_query = (db
            .collection('exercises')
            .document(exercise_id)
            .collection('analyses')
            .where('user_id', '==', user_id))

        # Add timestamp filter if provided
        if since_dt:
            analyses_query = analyses_query.where('timestamp', '>', since_dt)

        # Order by timestamp descending and limit to 1
        analyses_query = analyses_query.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(1)

        # Execute query
        analyses = analyses_query.get()
        doc_list = list(analyses)

        # Check if any document matched the criteria
        if not doc_list:
            message = f"No analysis found for user {user_id}, exercise {exercise_id}"
            if since_timestamp_str:
                message += f" since {since_timestamp_str}."
            else:
                message += "."
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
