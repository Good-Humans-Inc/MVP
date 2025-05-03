import functions_framework
import json
import logging
from datetime import datetime
import traceback
from google.cloud import firestore

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firestore DB
# Ensure the project and database name are correct for your environment
try:
    db = firestore.Client(project='pepmvp', database='pep-mvp')
    logger.info("Firestore client initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Firestore client: {e}", exc_info=True)
    db = None # Indicate client initialization failure

# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)

def _fetch_and_process_user_data(user_id, db_client):
    """
    Internal helper to retrieve user data from Firestore and derive notification_time string.
    Returns the user data dictionary on success, None otherwise.
    """
    if not user_id:
        logger.error("_fetch_and_process_user_data: Called with empty user_id")
        return None
    if not db_client:
        logger.error("_fetch_and_process_user_data: Called with no db_client")
        return None # Indicate DB client issue

    logger.info(f"🔄 _fetch_and_process_user_data: Fetching data for user_id: {user_id}")

    try:
        user_ref = db_client.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            logger.warning(f"❌ _fetch_and_process_user_data: User not found in Firestore: {user_id}")
            return None # Indicate user not found

        user_data = user_doc.to_dict()
        logger.info(f"📋 User data retrieved from Firestore for {user_id}")

        # --- Derive notification_time string ---
        notification_time_str = "" # Default to empty string
        prefs = user_data.get('notification_preferences') # Use .get for safety
        if isinstance(prefs, dict):
            hour = prefs.get('hour')
            minute = prefs.get('minute')
            # Ensure hour and minute are integers
            if isinstance(hour, int) and isinstance(minute, int) and 0 <= hour <= 23 and 0 <= minute <= 59:
                notification_time_str = f"{hour:02d}:{minute:02d}"
                logger.info(f"✅ Derived notification_time string for {user_id}: {notification_time_str}")
            else:
                logger.warning(f"⚠️ Found notification_preferences for {user_id} but hour/minute were invalid or missing: hour={hour}, minute={minute}")
        else:
            logger.info(f"📋 No valid notification_preferences found for {user_id}, setting notification_time to empty string.")

        # Add the derived string to the user_data dictionary
        user_data['notification_time'] = notification_time_str
        # --- End derivation ---

        logger.info(f"📋 Returning user_data for {user_id} including notification_time: '{notification_time_str}'")
        return user_data # Return fetched and processed data

    except Exception as e:
        logger.error(f"❌ Error processing _fetch_and_process_user_data for {user_id}: {str(e)}")
        logger.error(traceback.format_exc()) # Log stack trace
        return None # Indicate an internal error occurred


@functions_framework.http
def get_user_data(request):
    """
    HTTP Cloud Function to retrieve user data from Firestore.
    Expects 'user_id' as a query parameter.
    """
    # Set CORS headers for preflight requests
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Set CORS headers for main requests
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    # Check if Firestore client initialized correctly
    if db is None:
        logger.error("Firestore client is not available.")
        return (json.dumps({'error': 'Internal server error: Database connection failed'}), 500, headers)

    # Get user_id from request query parameters
    user_id = request.args.get('user_id')
    if not user_id:
        logger.warning("get_user_data: Missing user_id query parameter")
        return (json.dumps({'error': 'Missing user_id query parameter'}), 400, headers)

    logger.info(f"get_user_data: Processing request for user_id: {user_id}")

    try:
        user_data = _fetch_and_process_user_data(user_id, db)

        if user_data is not None:
            # User found and data processed successfully
            response_payload = {
                "success": True,
                "user_data": user_data
            }
            logger.info(f"✅ Successfully retrieved data for user {user_id}")
            return (json.dumps(response_payload, cls=DateTimeEncoder), 200, headers)
        else:
            # User not found or internal error during fetch/process
            logger.warning(f"⚠️ User not found or error processing data for user {user_id}")
            # We return 404 whether user not found or DB error, as requested by frontend potentially
            return (json.dumps({'error': 'User not found or error retrieving data'}), 404, headers)

    except Exception as e:
        logger.error(f"❌ Unexpected error in get_user_data for {user_id}: {str(e)}", exc_info=True)
        return (json.dumps({'error': 'Internal server error'}), 500, headers) 