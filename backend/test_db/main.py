import functions_framework
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@functions_framework.cloud_event
def monitor_db_changes(cloud_event):
    """Triggered by a change to a Firestore document."""
    logger.info("🔔 FUNCTION TRIGGERED - STARTING EXECUTION")
    
    # Log the event data
    logger.info(f"Event ID: {cloud_event.id}")
    logger.info(f"Event Type: {cloud_event.type}")
    logger.info(f"Event Source: {cloud_event.source}")
    logger.info(f"Event Subject: {cloud_event.subject}")
    
    # Extract document path from event data
    if hasattr(cloud_event, 'data') and cloud_event.data:
        try:
            # Extract document path information
            path_parts = cloud_event.data["value"]["name"].split("/documents/")[1].split("/")
            collection_path = path_parts[0]
            document_path = "/".join(path_parts[1:])
            
            logger.info(f"📄 Document change in collection: {collection_path}, document: {document_path}")
            
            # Get the changed document data
            if "fields" in cloud_event.data["value"]:
                changed_data = cloud_event.data["value"]["fields"]
                logger.info(f"📊 Document data: {json.dumps(changed_data, indent=2)}")
            else:
                logger.info("❌ No fields found in document change")
                
        except Exception as e:
            logger.error(f"❌ Error processing event data: {str(e)}")
            import traceback
            logger.error(f"📋 Stack trace: {traceback.format_exc()}")
    else:
        logger.warning("❓ No data found in cloud event")
    
    logger.info("✅ Function execution completed")
    return "OK"