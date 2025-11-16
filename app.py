"""
Flask Web Interface for TV Series Organizer
"""

import os
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session
from organize_series import (
    get_directory_tree,
    call_deepseek_api,
    generate_preview_tree,
    organize_files
)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuration
WORKSPACE = Path(__file__).parent
TV_UNORDERED = WORKSPACE / "tv_unordered"
TV = WORKSPACE / "tv"


@app.route('/')
def index():
    """Main page - list all folders in tv_unordered"""
    
    # Check if directories exist
    if not TV_UNORDERED.exists():
        TV_UNORDERED.mkdir(parents=True)
    
    TV.mkdir(exist_ok=True)
    
    # Get all folders
    folders = [f.name for f in TV_UNORDERED.iterdir() if f.is_dir()]
    
    # Check API key
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    has_api_key = bool(api_key)
    
    return render_template('index.html', 
                         folders=folders, 
                         has_api_key=has_api_key)


@app.route('/analyze', methods=['POST'])
def analyze():
    """Analyze a folder and return preview"""
    
    data = request.json
    folder_name = data.get('folder')
    api_key = data.get('api_key') or os.getenv("DEEPSEEK_API_KEY")
    
    if not folder_name:
        return jsonify({'error': 'No folder specified'}), 400
    
    if not api_key:
        return jsonify({'error': 'API key is required'}), 400
    
    # Get directory tree
    folder_path = TV_UNORDERED / folder_name
    if not folder_path.exists():
        return jsonify({'error': 'Folder not found'}), 404
    
    try:
        # Get tree
        tree = get_directory_tree(str(folder_path))
        
        # Call LLM
        structure = call_deepseek_api(api_key, tree, folder_name)
        
        # Generate preview
        preview = generate_preview_tree(structure, str(TV))
        
        # Store structure in session for later use
        session['structure'] = structure
        session['source_folder'] = str(folder_path)
        
        return jsonify({
            'success': True,
            'series_name': structure['series_name'],
            'year': structure['year'],
            'episodes_count': len(structure['episodes']),
            'original_tree': tree,
            'preview_tree': preview,
            'structure': structure
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/apply', methods=['POST'])
def apply():
    """Apply the organization"""
    
    # Get structure from session
    structure = session.get('structure')
    source_folder = session.get('source_folder')
    
    if not structure or not source_folder:
        return jsonify({'error': 'No pending organization'}), 400
    
    try:
        # Apply organization
        organize_files(structure, source_folder, str(TV), dry_run=False)
        
        # Clear session
        session.pop('structure', None)
        session.pop('source_folder', None)
        
        return jsonify({
            'success': True,
            'message': 'Organization applied successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/cancel', methods=['POST'])
def cancel():
    """Cancel pending organization"""
    
    session.pop('structure', None)
    session.pop('source_folder', None)
    
    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9002, debug=True)
