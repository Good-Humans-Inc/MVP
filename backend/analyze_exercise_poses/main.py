import functions_framework
from firebase_admin import initialize_app, firestore
import firebase_admin
import json
import os
from google.cloud import storage
from google.cloud import secretmanager
import base64
from datetime import datetime, timezone
from openai import OpenAI
import logging

# --- Constants ---
# Replace with your actual Google Cloud Storage bucket name
GCS_BUCKET_NAME = "your-gcs-bucket-name" 
# ---

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin
try:
    initialize_app()
    logger.info("Firebase Admin SDK initialized successfully.")
except ValueError:
    logger.warning("Firebase Admin SDK already initialized.")
    pass

# Initialize Cloud Storage client
try:
    storage_client = storage.Client()
    logger.info("Google Cloud Storage client initialized successfully.")
except Exception as e:
    logger.error(f"Error initializing Google Cloud Storage client: {str(e)}")
    raise

# Initialize Firestore DB Client (reuse if already initialized by firebase_admin)
try:
    db = firestore.Client(project='pepmvp', database='pep-mvp')
    logger.info("Firestore client initialized successfully.")
except Exception as e:
    logger.error(f"Error initializing Firestore client: {str(e)}")
    # Decide if we should raise here or rely on firebase_admin's initialization
    pass 


# Debug: Print environment variables
# print("Environment variables:")
# for key, value in os.environ.items():
#     if 'key' in key.lower():
#         # Print masked version of sensitive values
#         print(f"{key}: {'*' * 8}")
#     else:
#         print(f"{key}: {value}")

def access_secret_version(secret_id, version_id="latest"):
    """
    Access the secret from GCP Secret Manager
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.getenv("GCP_PROJECT", "pepmvp") # Get project ID from env or default
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        # Strip whitespace and newlines to avoid issues with API keys
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error accessing secret '{secret_id}': {str(e)}")
        raise

# Get OpenAI API key from Secret Manager
try:
    logger.info("Fetching OpenAI API key from Secret Manager...")
    openai_api_key = access_secret_version("openai-api-key")
    logger.info("Successfully retrieved OpenAI API key.") # Removed "from Secret Manager" for brevity
except Exception as e:
    logger.error(f"Failed to retrieve OpenAI API key: {str(e)}")
    # Decide if function should continue without OpenAI key or raise
    raise # Raising ensures the function fails if key is unavailable

# Initialize OpenAI client
try:
    logger.info("Initializing OpenAI client...")
    openai_client = OpenAI( # Renamed client to avoid conflict with storage_client etc.
        api_key=openai_api_key,
        timeout=60.0 # Consider making timeout configurable
    )
    logger.info("OpenAI client initialized successfully.")
except Exception as e:
    logger.error(f"Error initializing OpenAI client: {str(e)}")
    raise


def upload_image_to_gcs(image_bytes, destination_blob_name):
    """Uploads image bytes to the specified GCS bucket."""
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        
        # Determine content type (assuming JPEG)
        content_type = 'image/jpeg' 
        
        logger.info(f"☁️ Uploading image to gs://{GCS_BUCKET_NAME}/{destination_blob_name}...")
        blob.upload_from_string(image_bytes, content_type=content_type)
        
        # Make the blob publicly viewable (optional, adjust permissions as needed)
        # Consider using signed URLs for more controlled access
        blob.make_public() 
        
        public_url = blob.public_url
        logger.info(f"✅ Image uploaded successfully. Public URL: {public_url}")
        return public_url
    except Exception as e:
        logger.error(f"❌ Failed to upload image to GCS: {str(e)}")
        # Decide on error handling: return None, raise, etc.
        return None # Return None to indicate failure


def call_LLM(images_base64, prompt): # Renamed 'images' -> 'images_base64' for clarity
    """Call GPT-4 Vision API with images and prompt."""

    # Convert base64 images to URLs or direct base64
    image_contents = []
    for idx, image_base64 in enumerate(images_base64, start=1): # Use the renamed parameter
        # Basic validation: check if it looks like base64
        if not isinstance(image_base64, str) or len(image_base64) < 10:
             logger.warning(f"⚠️ Skipping invalid image data at index {idx}.")
             continue
        image_contents.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
                "detail": "low", # Use low detail to reduce tokens
                #"sequence": idx # Sequence might not be supported or necessary
            }
        })

    if not image_contents:
        logger.error("❌ No valid images provided to LLM.")
        raise ValueError("No valid image data found for LLM processing.")

    try:
        logger.info(f"🤖 Calling LLM with {len(image_contents)} images...")
        # logger.debug(f"📝 Prompt: {prompt}") # Log prompt only in debug if needed

        response = openai_client.chat.completions.create( # Use renamed openai_client
            model="gpt-4o-mini", # Specify the exact model
            messages=[
                {
                    "role": "system", # Add a system message for context
                    "content": "You are a helpful physical therapy assistant providing exercise feedback."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_contents
                    ]
                }
            ],
            max_tokens=300 # Limit response length
        )

        # Extract the response content
        if response.choices and response.choices[0].message:
            analysis_text = response.choices[0].message.content
            logger.info("🔍 Raw LLM Response received.")
            # logger.debug(f"LLM Response:\n{analysis_text}") # Log full response only if needed
            return {
                'raw_response': analysis_text.strip() if analysis_text else "No feedback provided."
            }
        else:
            logger.error("❌ LLM response was empty or invalid.")
            return {
                 'raw_response': "Error: Failed to get feedback from analysis model."
            }

    except Exception as e:
        logger.error(f"❌ Error calling LLM: {str(e)}")
        raise # Re-raise to be caught by the main handler


def store_analysis(user_id, exercise_id, analysis_id, analysis_data, image_urls): # Added analysis_id and image_urls
    """Store the analysis results (including image URLs) in Firestore."""
    try:
        # Use the global db client initialized earlier
        # db = firestore.Client(project='pepmvp', database='pep-mvp') # No need to re-initialize

        # Reference the specific document using the pre-generated ID
        analysis_ref = db.collection('exercises').document(exercise_id) \
                         .collection('analyses').document(analysis_id)

        # Combine LLM analysis with other data
        firestore_data = {
            'timestamp': firestore.SERVER_TIMESTAMP,
            'user_id': user_id,
            'raw_response': analysis_data['raw_response'],
            'image_urls': image_urls # Add the list of image URLs
        }

        logger.info(f"💾 Storing analysis data to Firestore document: {analysis_ref.path}")
        # logger.debug(f"Firestore Data: {firestore_data}") # Log data only if needed

        # Set the data in Firestore
        analysis_ref.set(firestore_data)

        logger.info(f"✅ Analysis stored successfully in Firestore: {analysis_ref.path}")
        # No need to return analysis_id, it was generated earlier

    except Exception as e:
        logger.error(f"❌ Error storing analysis to Firestore: {str(e)}")
        raise # Re-raise the exception


@functions_framework.http
def analyze_exercise_poses(request):
    """
    HTTP Cloud Function to analyze exercise poses, upload images to GCS,
    and store analysis results (including image URLs) in Firestore.
    Returns success status and the ID of the created analysis document.
    """
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS', # Allow POST and OPTIONS
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Default headers for actual response
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    try:
        request_json = request.get_json(silent=True) # Use silent=True for better error handling

        if not request_json:
            logger.error("Request processing failed: No JSON data provided.")
            return {'error': 'No JSON data provided'}, 400, headers

        # --- Validate Input ---
        images_base64 = request_json.get('images')
        exercise_info = request_json.get('exerciseInfo')

        if not isinstance(images_base64, list) or not images_base64:
             logger.error("Request processing failed: 'images' field is missing or not a non-empty list.")
             return {'error': "'images' must be a non-empty list"}, 400, headers

        if not isinstance(exercise_info, dict):
             logger.error("Request processing failed: 'exerciseInfo' field is missing or not an object.")
             return {'error': "'exerciseInfo' must be an object"}, 400, headers

        required_fields = ['userId', 'exerciseId', 'name', 'instructions']
        missing_fields = [field for field in required_fields if field not in exercise_info or not exercise_info[field]]

        if missing_fields:
            error_msg = f'Missing or empty required fields in exerciseInfo: {", ".join(missing_fields)}'
            logger.error(f"Request processing failed: {error_msg}")
            return {'error': error_msg}, 400, headers

        user_id = exercise_info['userId']
        exercise_id = exercise_info['exerciseId']
        exercise_name = exercise_info['name']
        exercise_instructions = exercise_info['instructions']

        logger.info(f"🚀 Received analysis request for User: {user_id}, Exercise: {exercise_id} ({exercise_name}) with {len(images_base64)} images.")

        # --- Record Request Timestamp ---
        request_received_time = datetime.now(timezone.utc)
        status_doc_ref = db.collection('user_analysis_status').document(user_id)
        try:
            # Overwrite the timestamp for this user
            status_doc_ref.set({
                'last_request_timestamp': request_received_time,
                'status': 'processing' # Optional: add status
            }, merge=True) # Use merge=True if adding optional fields later
            logger.info(f"⏱️ Recorded request timestamp for user {user_id} at {request_received_time.isoformat()}")
        except Exception as e_status:
            # Log error but proceed with analysis if status write fails
            logger.error(f"⚠️ Failed to write request timestamp status for user {user_id}: {e_status}")


        # --- Generate Analysis ID ---
        analysis_ref = db.collection('exercises').document(exercise_id) \
                         .collection('analyses').document()
        analysis_id = analysis_ref.id
        logger.info(f"🔑 Generated Analysis ID: {analysis_id}")


        # --- Upload Images to GCS ---
        uploaded_image_urls = []
        for i, img_b64 in enumerate(images_base64):
            try:
                # Decode Base64 image
                image_bytes = base64.b64decode(img_b64)
                
                # Define destination path in GCS
                blob_name = f"users/{user_id}/exercises/{exercise_id}/analyses/{analysis_id}/frame_{i+1}.jpg"
                
                # Upload and get URL
                public_url = upload_image_to_gcs(image_bytes, blob_name)
                if public_url:
                    uploaded_image_urls.append(public_url)
                else:
                    # Handle upload failure for a single image - decide whether to continue or fail all
                    logger.warning(f"⚠️ Failed to upload image {i+1} for analysis {analysis_id}. Skipping this image.")
                    # Optionally: return error immediately
                    # return {'error': f'Failed to upload image {i+1}'}, 500, headers

            except (base64.binascii.Error, TypeError) as decode_error:
                logger.warning(f"⚠️ Failed to decode base64 image at index {i} for analysis {analysis_id}: {decode_error}. Skipping.")
                # Continue processing other images or fail the request
            except Exception as upload_error: # Catch broader exceptions during upload
                 logger.error(f"❌ Unexpected error uploading image {i+1}: {upload_error}")
                 # Optionally fail the entire request here

        # Check if any images were successfully uploaded
        if not uploaded_image_urls and images_base64: # If input had images but none were uploaded
             logger.error("❌ No images were successfully uploaded to GCS.")
             return {'error': 'Failed to process and upload images.'}, 500, headers


        # --- Call LLM for Analysis ---
        prompt = f"""Analyze the user performing: {exercise_name}
Instructions: {exercise_instructions}

Sequence of {len(images_base64)} images provided. Assess correctness based on the sequence.
Focus on: Major issues, how to fix them. What's done well.
Output: Be concise (2-3 sentences max). Format with clear "Issues" and "Suggestions" sections using bullet points if applicable. Acknowledge the limitations of snapshots vs full video.
"""
        analysis_result = call_LLM(images_base64, prompt) # Pass original base64 images


        # --- Store Analysis in Firestore ---
        store_analysis(
            user_id=user_id,
            exercise_id=exercise_id,
            analysis_id=analysis_id,
            analysis_data=analysis_result,
            image_urls=uploaded_image_urls
        )
        # Optional: Update status document to 'complete'
        try:
             status_doc_ref.set({'status': 'complete'}, merge=True)
        except Exception as e_status_complete:
             logger.warning(f"⚠️ Failed to update status to complete for user {user_id}: {e_status_complete}")


        logger.info(f"✅ Successfully processed analysis request {analysis_id}.")
        return {
            'success': True,
            'message': 'Analysis complete, images uploaded, and results stored.',
            'analysisId': analysis_id
        }, 200, headers

    except Exception as e:
        # Log the exception traceback for detailed debugging if needed
        # import traceback
        # logger.error(f"Unhandled exception: {traceback.format_exc()}")
        logger.error(f"❌ Critical error in analyze_exercise_poses: {str(e)}")
        # Optional: Update status document to 'failed' on critical error
        if 'user_id' in locals() and user_id: # Check if user_id was extracted
             try:
                  db.collection('user_analysis_status').document(user_id).set({'status': 'failed'}, merge=True)
             except Exception as e_status_fail:
                  logger.error(f"⚠️ Failed to update status to failed for user {user_id}: {e_status_fail}")
        return {
            'success': False, # Indicate failure clearly
            'error': 'Internal server error occurred.',
            'message': str(e) # Provide error details (consider security implications)
        }, 500, headers

# Note: main.py might need further adjustments for specific error handling,
# security (e.g., using signed URLs instead of public URLs), and configuration.
# Remember to replace "your-gcs-bucket-name" with your actual bucket name.
