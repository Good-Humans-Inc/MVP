import firebase_admin
from firebase_admin import credentials, firestore
from flask import jsonify, request
from flask_cors import cross_origin
import os
import json
import logging

# Initialize Firebase Admin
if not firebase_admin._apps:
    project_id = "pepmvp"
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        'projectId': project_id,
    })

db = firestore.Client(project='pepmvp', database='pep-mvp')

@cross_origin()
def update_fcm_token(request):
    """
    Updates the FCM token for a given user in Firestore.
    
    Args:
        request (flask.Request): The request object containing:
            - user_id: The ID of the user
            - fcm_token: The new FCM token to store
            
    Returns:
        flask.Response: JSON response indicating success or failure
    """
    try:
        # Set CORS headers for preflight requests
        if request.method == 'OPTIONS':
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '3600'
            }
            return ('', 204, headers)

        request_json = request.get_json()
        
        if not request_json:
            return jsonify({
                'success': False,
                'error': 'No request data provided'
            }), 400

        user_id = request_json.get('user_id')
        fcm_token = request_json.get('fcm_token')

        if not user_id or not fcm_token:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: user_id and fcm_token'
            }), 400

        # Update the user's FCM token in Firestore
        user_ref = db.collection('users').document(user_id)
        user_ref.update({
            'fcm_token': fcm_token,
            'last_token_update': firestore.SERVER_TIMESTAMP
        })

        return jsonify({
            'success': True,
            'message': 'FCM token updated successfully'
        })

    except Exception as e:
        logging.error(f"Error updating FCM token: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to update FCM token: {str(e)}'
        }), 500 