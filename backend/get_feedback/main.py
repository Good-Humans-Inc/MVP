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
    Expects a GET request with query parameters:
    - userId: string
    - exerciseId: string
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
        user_id = request.args.get('userId')
        exercise_id = request.args.get('exerciseId')
        
        if not user_id or not exercise_id:
            return {
                'error': 'Missing required parameters. Need userId and exerciseId'
            }, 400, headers

        # Initialize Firestore DB with specific project and database
        db = firestore.Client(project='pepmvp', database='pep-mvp')
        
        # Query the latest analysis from the new structure
        analyses_ref = (db
            .collection('exercises')
            .document(exercise_id)
            .collection('analyses')
            .where('user_id', '==', user_id)  # Filter by user_id
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(1))
        
        analyses = analyses_ref.get()
        
        if not analyses or len(list(analyses)) == 0:
            return {
                'success': True,
                'hasAnalysis': False,
                'message': "No analysis found"
            }, 200, headers
        
        # Get the latest analysis
        latest_analysis = list(analyses)[0].to_dict()
        
        return {
            'success': True,
            'hasAnalysis': True,
            'feedback': latest_analysis.get('raw_response', '')
        }, 200, headers

    except Exception as e:
        print(f"❌ Error in get_latest_feedback: {str(e)}")
        return {
            'error': 'Internal server error',
            'message': str(e)
        }, 500, headers
