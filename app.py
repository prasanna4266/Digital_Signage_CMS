import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId # For MongoDB document IDs
from datetime import datetime # Import datetime here for consistent use
from flask_cors import CORS # Import CORS
import gridfs # Import gridfs
from gridfs import GridFSBucket # Import GridFSBucket for cleaner file handling
import logging#
# Import configuration
from config import Config

app = Flask(__name__, instance_relative_config=True)
app.config.from_object(Config)
CORS(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- MongoDB Setup ---
client = MongoClient(app.config['MONGO_URI'])
db = client[app.config['MONGO_DB_NAME']]

# Collections (equivalent to tables in SQL)
content_collection = db.content
screens_collection = db.screens

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- Routes ---

@app.route('/')
def index():
    app.logger.debug("Accessing index page.")
    # Fetch content and convert _id to a string 'id' for the template
    content_cursor = content_collection.find().sort("upload_date", -1)
    content = []
    for item in content_cursor:
        item['id'] = str(item['_id']) # Convert ObjectId to string for template
        content.append(item)
    app.logger.debug(f"Fetched {len(content)} content items.")

    # Fetch screens and join with content details
    screens_cursor = screens_collection.aggregate([
        {
            '$lookup': {
                'from': 'content',
                'localField': 'assigned_content_id',
                'foreignField': '_id',
                'as': 'assigned_content'
            }
        },
        {
            '$unwind': {
                'path': '$assigned_content',
                'preserveNullAndEmptyArrays': True
            }
        },
        {
            '$project': {
                '_id': 0, # Exclude original _id from screen doc if not needed
                'id': '$_id', # Map _id to id for consistency in screens
                'assigned_content_id': '$assigned_content_id',
                'filename': '$assigned_content.filename'
            }
        }
    ])
    screens = list(screens_cursor)
    app.logger.debug(f"Fetched {len(screens)} screens.")

    return render_template('index.html', content=content, screens=screens)


@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath_on_disk = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath_on_disk)

            # Store content info in MongoDB
            content_data = {
                'filename': filename,
                'filepath': f'/static/uploads/{filename}', # This is the web path
                'mimetype': file.mimetype,
                'upload_date': datetime.now() # Store datetime object
            }
            inserted_id = content_collection.insert_one(content_data).inserted_id
            
            flash('File successfully uploaded')
            return redirect(url_for('index'))
        else:
            flash('Allowed file types are ' + ', '.join(app.config['ALLOWED_EXTENSIONS']))
            return redirect(request.url)
    return render_template('upload.html')

@app.route('/delete_content/<string:content_id>', methods=['POST'])
def delete_content(content_id):
    try:
        obj_id = ObjectId(content_id)
    except:
        flash('Invalid content ID.')
        return redirect(url_for('index'))

    # Check if any screen is assigned this content
    screen_count = screens_collection.count_documents({'assigned_content_id': obj_id})
    if screen_count > 0:
        flash(f'Cannot delete content: It is currently assigned to {screen_count} screen(s).')
        return redirect(url_for('index'))

    # Get filename to delete from disk
    content_item = content_collection.find_one({'_id': obj_id})
    if content_item:
        filename = content_item['filename']
        file_path_on_disk = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path_on_disk):
            os.remove(file_path_on_disk)

        content_collection.delete_one({'_id': obj_id})
        flash('Content deleted successfully.')
    else:
        flash('Content not found.')
    return redirect(url_for('index'))


@app.route('/manage_screens', methods=['GET', 'POST'])
def manage_screens():
    # Fetch screens with joined content details
    screens_cursor = screens_collection.aggregate([
        {
            '$lookup': {
                'from': 'content',
                'localField': 'assigned_content_id',
                'foreignField': '_id',
                'as': 'assigned_content'
            }
        },
        {
            '$unwind': {
                'path': '$assigned_content',
                'preserveNullAndEmptyArrays': True
            }
        },
        {
            '$project': {
                'id': '$_id',
                'assigned_content_id': '$assigned_content_id',
                'filename': '$assigned_content.filename'
            }
        }
    ])
    screens = list(screens_cursor)
    content = list(content_collection.find()) # All content items
    return render_template('screens.html', screens=screens, content=content)

@app.route('/assign_content', methods=['POST'])
def assign_content():
    screen_id = request.form['screen_id']
    content_id = request.form['content_id']

    # --- ADD DEBUG PRINTS HERE ---
    app.logger.debug(f"Assign Content: Received screen_id: '{screen_id}', content_id: '{content_id}'")

    try:
        obj_content_id = ObjectId(content_id) if content_id else None
        app.logger.debug(f"Assign Content: Converted content_id to ObjectId: {obj_content_id}")
    except Exception as e: # Catch specific exception for better error handling
        flash(f'Invalid content ID selected: {e}')
        app.logger.error(f"Assign Content: Error converting content_id '{content_id}' to ObjectId: {e}")
        return redirect(url_for('manage_screens'))

    # Check if screen exists (not strictly necessary with upsert=True, but good for logging)
    existing_screen = screens_collection.find_one({'_id': screen_id})
    if not existing_screen:
        app.logger.debug(f"Assign Content: Screen '{screen_id}' does not exist, will be upserted.")
    else:
        app.logger.debug(f"Assign Content: Screen '{screen_id}' already exists. Current content: {existing_screen.get('assigned_content_id')}")

    # Assign content
    result = screens_collection.update_one(
        {'_id': screen_id}, # Use screen_id directly as _id
        {'$set': {'assigned_content_id': obj_content_id}},
        upsert=True # Creates the document if it doesn't exist
    )
    app.logger.debug(f"Assign Content: MongoDB update result: Matched={result.matched_count}, Modified={result.modified_count}, UpsertedId={result.upserted_id}")
    
    # --- VERIFY AFTER UPDATE ---
    updated_screen_data = screens_collection.find_one({'_id': screen_id})
    if updated_screen_data:
        app.logger.debug(f"Assign Content: Screen '{screen_id}' data after update: {updated_screen_data}")
        # Compare ObjectId if content_id is not empty, otherwise compare None
        if content_id and updated_screen_data.get('assigned_content_id') == obj_content_id:
            flash(f'Content assigned to screen {screen_id} successfully!')
        elif not content_id and updated_screen_data.get('assigned_content_id') is None:
             flash(f'Content unassigned from screen {screen_id} successfully!')
        else:
            flash(f'Content assignment to screen {screen_id} failed verification!')
            app.logger.error(f"Assign Content: Verification failed for screen {screen_id}. Expected {obj_content_id}, got {updated_screen_data.get('assigned_content_id')}")
    else:
        flash(f'Screen {screen_id} not found after assignment attempt!')
        app.logger.error(f"Assign Content: Screen {screen_id} not found after update_one call.")
    # --- END VERIFY ---
    
    return redirect(url_for('manage_screens'))


@app.route('/delete_screen/<string:screen_id>', methods=['POST'])
def delete_screen(screen_id):
    screens_collection.delete_one({'_id': screen_id})
    flash(f'Screen {screen_id} deleted.')
    return redirect(url_for('manage_screens'))


# --- API Endpoint for Screens to Fetch Content ---
# In your app.py

@app.route('/api/screen/<string:screen_id>')
def get_screen_content(screen_id):
    app.logger.debug(f"API request for screen content: {screen_id}")
    screen_data = screens_collection.find_one({'_id': screen_id})

    response_data = {
        'screen_id': screen_id,
        'content': None # Initialize content as None
    }

    if screen_data: # If screen exists (it either has content or is unassigned)
        assigned_content_id = screen_data.get('assigned_content_id')
        
        if assigned_content_id: # If content is assigned
            assigned_content = content_collection.find_one({'_id': assigned_content_id})
            
            if assigned_content: # If assigned content actually exists in the content collection
                media_url = url_for('static', filename=f'uploads/{assigned_content["filename"]}', _external=True)
                
                response_data['content'] = {
                    'content_id': str(assigned_content['_id']), # Add content_id for client-side comparison
                    'filename': assigned_content['filename'],
                    'url': media_url,
                    'mimetype': assigned_content['mimetype']
                }
                app.logger.info(f"Screen {screen_id}: Assigned content '{assigned_content['filename']}' found.")
            else:
                # Screen has an assigned_content_id, but the actual content is missing.
                # This state means content was deleted after assignment.
                response_data['message'] = 'Assigned content not found. Content may have been deleted.'
                app.logger.warning(f"Screen {screen_id}: assigned_content_id '{assigned_content_id}' exists but content not found in DB.")
        else:
            # Screen exists, but no content is assigned to it (assigned_content_id is None).
            response_data['message'] = 'No content assigned yet.'
            app.logger.info(f"Screen {screen_id}: No content currently assigned.")
    else:
        # If screen ID doesn't exist, auto-register it
        screens_collection.insert_one({'_id': screen_id, 'assigned_content_id': None})
        response_data['message'] = 'Screen registered. No content assigned yet.'
        app.logger.info(f"Screen {screen_id} auto-registered.")
        # No need for an immediate return jsonify here, as the final return will handle it.

    # This ensures a response is always returned, regardless of the path taken
    return jsonify(response_data)
# In your app.py
@app.route('/display/<string:screen_id_param>')
def display_screen(screen_id_param):
    # This function tells Flask to render the Abcd.html template
    # when a user accesses /display/some_screen_id
    return render_template('Abcd.html', screen_id=screen_id_param)


    return jsonify(response_data)

if __name__ == '__main__':
    app.run(debug=True) # Set debug=False in production!