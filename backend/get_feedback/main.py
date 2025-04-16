import functions_framework
from firebase_admin import initialize_app, firestore
import firebase_admin

# Initialize Firebase Admin
try:
    initialize_app()
except ValueError:
    # App already initialized
    pass

@functions_framework.http
def get_latest_feedback(request):
    """
    HTTP Cloud Function to get the latest feedback for a user's exercise.
    Expects a POST request with JSON body containing:
    {
        "userId": "string",
        "exerciseId": "string"
    }
    """
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    try:
        request_json = request.get_json()
        
        if not request_json:
            return {'error': 'No JSON data provided'}, 400, headers
        
        user_id = request_json.get('userId')
        exercise_id = request_json.get('exerciseId')
        
        if not user_id or not exercise_id:
            return {
                'error': 'Missing required parameters. Need userId and exerciseId'
            }, 400, headers

        # Get Firestore client
        db = firestore.client()
        
        # Query the latest analysis
        analyses_ref = (db
            .collection('users')
            .document(user_id)
            .collection('exercises')
            .document(exercise_id)
            .collection('analyses')
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(1))
        
        analyses = analyses_ref.get()
        
        if not analyses or len(analyses) == 0:
            return {
                'success': True,
                'hasAnalysis': False,
                'message': "No analysis found"
            }, 200, headers
        
        # Get the latest analysis and return raw data
        latest_analysis = analyses[0].to_dict()
        
        return {
            'success': True,
            'hasAnalysis': True,
            'issues': latest_analysis.get('issues', []),
            'suggestions': latest_analysis.get('suggestions', [])
        }, 200, headers

    except Exception as e:
        print(f"Error in get_latest_feedback: {str(e)}")
        return {
            'error': 'Internal server error',
            'message': str(e)
        }, 500, headers
