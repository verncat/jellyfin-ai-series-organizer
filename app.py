"""
Flask Web Interface for TV Series Organizer
"""

import os
import json
import logging
import shutil
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, Response
from organize_series import (
    get_directory_tree,
    call_deepseek_api,
    generate_preview_tree
)

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    
    # Get all folders with file counts
    folders = []
    for folder in TV_UNORDERED.iterdir():
        if folder.is_dir():
            # Count video files (.mkv, .mp4, .avi)
            video_files = list(folder.glob('*.mkv')) + list(folder.glob('*.mp4')) + list(folder.glob('*.avi'))
            
            # Check if already applied
            mapping_file = folder / 'file_mappings.json'
            applied_info = None
            if mapping_file.exists():
                try:
                    mapping_data = json.loads(mapping_file.read_text())
                    applied_info = {
                        'applied_at': mapping_data.get('applied_at'),
                        'destination': mapping_data.get('destination_folder'),
                        'file_count': len(mapping_data.get('file_mappings', []))
                    }
                except Exception as e:
                    logger.error(f"Error reading mapping file {mapping_file}: {e}")
            
            folders.append({
                'name': folder.name,
                'file_count': len(video_files),
                'applied': applied_info
            })
    
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


@app.route('/apply', methods=['GET'])
def apply():
    """Apply the organization with progress tracking"""
    
    # Get structure from session
    structure = session.get('structure')
    source_folder = session.get('source_folder')
    
    if not structure or not source_folder:
        return jsonify({'error': 'No pending organization'}), 400
    
    def generate():
        """Generator for streaming progress"""
        try:
            logger.info("=== Starting apply_organization ===")
            logger.info(f"Source folder: {source_folder}")
            logger.info(f"Structure: {json.dumps(structure, indent=2)}")
            
            from pathlib import Path
            import shutil
            
            series_name = structure['series_name']
            year = structure['year']
            folder_name = f"{series_name} ({year})" if year else series_name
            
            series_path = Path(str(TV)) / folder_name
            logger.info(f"Series path: {series_path}")
            
            total_files = 0
            moved_files = 0
            
            # Count total files (episodes + related files)
            import glob as glob_module
            logger.info(f"Counting files from {len(structure['episodes'])} episodes...")
            for ep in structure['episodes']:
                source_file = Path(source_folder) / ep['original_filename']
                logger.info(f"Checking: {source_file}")
                logger.info(f"Exists: {source_file.exists()}")
                if source_file.exists():
                    # Count related files
                    source_stem = source_file.stem
                    source_parent = source_file.parent
                    escaped_stem = glob_module.escape(source_stem)
                    related = list(source_parent.glob(f"{escaped_stem}.*"))
                    logger.info(f"Related files for {source_stem}: {[f.name for f in related]}")
                    total_files += len(related)
            
            logger.info(f"Total files to move: {total_files}")
            # Send total count
            yield f"data: {json.dumps({'type': 'total', 'total': total_files})}\n\n"
            
            # Track file mappings for all files
            all_file_mappings = []
            
            # Process files
            logger.info(f"Starting to process {len(structure['episodes'])} episodes")
            for ep in structure['episodes']:
                season_num = ep['season']
                season_folder = series_path / f"Season {season_num:02d}"
                
                # Find source file
                source_file = Path(source_folder) / ep['original_filename']
                logger.info(f"Processing episode: {ep['original_filename']}")
                logger.info(f"Source file path: {source_file}")
                logger.info(f"Source file exists: {source_file.exists()}")
                
                if not source_file.exists():
                    logger.warning(f"Source file not found, skipping: {source_file}")
                    continue
                
                dest_file = season_folder / ep['new_filename']
                logger.info(f"Destination: {dest_file}")
                logger.info(f"Creating season folder: {season_folder}")
                season_folder.mkdir(parents=True, exist_ok=True)
                
                # Collect all related files BEFORE moving anything
                source_stem = source_file.stem
                source_parent = source_file.parent
                dest_stem = dest_file.stem
                
                # Escape special glob characters in filename
                import glob as glob_module
                escaped_stem = glob_module.escape(source_stem)
                
                related_files = list(source_parent.glob(f"{escaped_stem}.*"))
                logger.info(f"Found {len(related_files)} files to move for {source_stem}")
                
                # Create hard links for all files (main + related)
                for file_to_move in related_files:
                    logger.info(f"Creating link for file: {file_to_move}")
                    if file_to_move == source_file:
                        # Create hard link for main video file
                        logger.info(f"Creating hard link: {file_to_move} -> {dest_file}")
                        
                        # Record mapping
                        all_file_mappings.append({
                            'old_path': str(file_to_move.relative_to(Path.cwd())),
                            'new_path': str(dest_file.relative_to(Path.cwd())),
                            'old_name': file_to_move.name,
                            'new_name': dest_file.name
                        })
                        
                        # Create hard link (preserves original file and permissions)
                        try:
                            os.link(str(file_to_move), str(dest_file))
                            moved_files += 1
                            logger.info(f"Hard link created successfully")
                        except OSError as e:
                            logger.error(f"Failed to create hard link, falling back to copy: {e}")
                            # Fallback to copy if hard link fails (e.g., cross-filesystem)
                            shutil.copy2(str(file_to_move), str(dest_file))
                            moved_files += 1
                        
                        yield f"data: {json.dumps({'type': 'progress', 'current': moved_files, 'total': total_files, 'filename': ep['new_filename']})}\n\n"
                    else:
                        # Create hard link for related file (keep same extension)
                        extension = file_to_move.suffix
                        related_dest = season_folder / f"{dest_stem}{extension}"
                        logger.info(f"Creating hard link for related file: {file_to_move} -> {related_dest}")
                        
                        # Record mapping
                        all_file_mappings.append({
                            'old_path': str(file_to_move.relative_to(Path.cwd())),
                            'new_path': str(related_dest.relative_to(Path.cwd())),
                            'old_name': file_to_move.name,
                            'new_name': related_dest.name
                        })
                        
                        # Create hard link (preserves original file and permissions)
                        try:
                            os.link(str(file_to_move), str(related_dest))
                            moved_files += 1
                            logger.info(f"Hard link created successfully")
                        except OSError as e:
                            logger.error(f"Failed to create hard link, falling back to copy: {e}")
                            # Fallback to copy if hard link fails
                            shutil.copy2(str(file_to_move), str(related_dest))
                            moved_files += 1
                        
                        yield f"data: {json.dumps({'type': 'progress', 'current': moved_files, 'total': total_files, 'filename': related_dest.name})}\n\n"
            
            # Create .applied marker and mapping file in source folder
            source_folder_path = Path(source_folder)
            applied_marker = source_folder_path / '.applied'
            mapping_file = source_folder_path / 'file_mappings.json'
            
            # Write .applied marker with timestamp
            from datetime import datetime
            applied_marker.write_text(f"Organization applied at {datetime.now().isoformat()}\n")
            
            # Write file mappings JSON
            mapping_data = {
                'applied_at': datetime.now().isoformat(),
                'series_name': structure['series_name'],
                'year': structure['year'],
                'destination_folder': str(series_path.relative_to(Path.cwd())),
                'file_mappings': all_file_mappings
            }
            mapping_file.write_text(json.dumps(mapping_data, indent=2))
            logger.info(f"Created {applied_marker} and {mapping_file}")
            logger.info(f"Saved {len(all_file_mappings)} file mappings")
            
            # Send completion
            logger.info(f"=== Completed: moved {moved_files} files ===")
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Organization applied successfully', 'total': moved_files})}\n\n"
            
        except Exception as e:
            logger.error(f"Error during organization: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/apply/complete', methods=['POST'])
def apply_complete():
    """Clear session after organization complete"""
    session.pop('structure', None)
    session.pop('source_folder', None)
    return jsonify({'success': True})


@app.route('/cancel', methods=['POST'])
def cancel():
    """Cancel pending organization"""
    
    session.pop('structure', None)
    session.pop('source_folder', None)
    
    return jsonify({'success': True})


@app.route('/revert', methods=['POST'])
def revert():
    """Revert organization by removing hard links (original files remain intact)"""
    try:
        data = request.json
        folder_name = data.get('folder')
        
        if not folder_name:
            return jsonify({'error': 'No folder specified'}), 400
        
        source_folder = TV_UNORDERED / folder_name
        mapping_file = source_folder / 'file_mappings.json'
        
        if not mapping_file.exists():
            return jsonify({'error': 'No mapping file found'}), 404
        
        # Read mapping
        mapping_data = json.loads(mapping_file.read_text())
        file_mappings = mapping_data.get('file_mappings', [])
        
        logger.info(f"Reverting {len(file_mappings)} links for folder: {folder_name}")
        
        files_reverted = 0
        errors = []
        
        # Remove hard links (original files stay in tv_unordered)
        for mapping in file_mappings:
            try:
                new_path = Path(mapping['new_path'])
                
                if new_path.exists():
                    # Simply delete the link - original file remains
                    new_path.unlink()
                    files_reverted += 1
                    logger.info(f"Removed link: {new_path}")
                else:
                    logger.warning(f"Link not found for revert: {new_path}")
                    
            except Exception as e:
                error_msg = f"Error removing link {mapping['new_name']}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Remove .applied marker and mapping file
        applied_marker = source_folder / '.applied'
        if applied_marker.exists():
            applied_marker.unlink()
        
        mapping_file.unlink()
        
        logger.info(f"Revert completed: {files_reverted} files reverted, {len(errors)} errors")
        
        return jsonify({
            'success': True,
            'files_reverted': files_reverted,
            'errors': errors
        })
        
    except Exception as e:
        logger.error(f"Error during revert: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9002, debug=True)
