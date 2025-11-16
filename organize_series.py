"""
TV Series Organizer with DeepSeek LLM
Automatically organizes TV series files from tv_unordered to tv directory
with proper structure using LLM for intelligent parsing.
"""

import os
import json
import shutil
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from openai import OpenAI


@dataclass
class Episode:
    """Episode file information"""
    original_path: str
    new_filename: str
    season: int
    episode: int


@dataclass
class SeriesStructure:
    """Organized series structure"""
    series_name: str
    year: Optional[int]
    episodes: List[Episode]


def get_directory_tree(path: str, prefix: str = "", max_depth: int = 3, current_depth: int = 0) -> str:
    """Generate tree structure of a directory"""
    if current_depth >= max_depth:
        return ""
    
    tree = []
    path_obj = Path(path)
    
    if not path_obj.exists():
        return ""
    
    items = sorted(path_obj.iterdir(), key=lambda x: (not x.is_dir(), x.name))
    
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        current_prefix = "└── " if is_last else "├── "
        tree.append(f"{prefix}{current_prefix}{item.name}")
        
        if item.is_dir() and current_depth < max_depth - 1:
            extension_prefix = "    " if is_last else "│   "
            subtree = get_directory_tree(
                str(item), 
                prefix + extension_prefix, 
                max_depth, 
                current_depth + 1
            )
            if subtree:
                tree.append(subtree)
    
    return "\n".join(tree)


def call_deepseek_api(api_key: str, directory_tree: str, folder_name: str) -> dict:
    """Call DeepSeek API to analyze series structure"""
    
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    
    prompt = f"""Analyze this TV series folder structure and organize it properly.

Folder name: {folder_name}
Directory tree:
{directory_tree}

Extract:
1. Series name (clean, without tags like [AniLibria.TV])
2. Release year (if identifiable, otherwise null)
3. For each video file (.mkv, .mp4, .avi):
   - Season number (if not clear, assume Season 01)
   - Episode number(s)
   - New standardized filename in format: "Series Name S##E##.ext"
   - Original file path

Rules:
- Use Season 00 for specials/OVA
- For multi-episode files use S##E##-E## format
- Keep extra info (like "Part 1") at the end
- Include all video files only (.mkv, .mp4, .avi)
- Use absolute numbering if seasons unclear

Return structured JSON."""

    system_prompt = """You are a TV series file organizer. Analyze the directory structure and return ONLY a valid JSON object with this exact structure:
{
    "series_name": "Clean series name without tags",
    "year": 2023 or null,
    "episodes": [
        {
            "original_filename": "exact filename from tree",
            "new_filename": "Series Name S01E01.mkv",
            "season": 1,
            "episode": 1
        }
    ]
}

Rules:
- Only include video files (.mkv, .mp4, .avi)
- year can be integer or null
- season and episode must be integers
- Return ONLY the JSON, no other text"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.3
    )
    
    return json.loads(response.choices[0].message.content)


def generate_preview_tree(structure: dict, base_path: str) -> str:
    """Generate preview tree of the organized structure"""
    series_name = structure['series_name']
    year = structure['year']
    folder_name = f"{series_name} ({year})" if year else series_name
    
    # Group episodes by season
    seasons = {}
    for ep in structure['episodes']:
        season_num = ep['season']
        if season_num not in seasons:
            seasons[season_num] = []
        seasons[season_num].append(ep['new_filename'])
    
    # Build tree
    tree_lines = [folder_name]
    sorted_seasons = sorted(seasons.keys())
    
    for i, season_num in enumerate(sorted_seasons):
        is_last_season = i == len(sorted_seasons) - 1
        season_prefix = "└── " if is_last_season else "├── "
        season_name = f"Season {season_num:02d}"
        tree_lines.append(f"{season_prefix}{season_name}")
        
        episodes = sorted(seasons[season_num])
        for j, episode in enumerate(episodes):
            is_last_ep = j == len(episodes) - 1
            ep_prefix = "    └── " if is_last_season else "│   └── " if is_last_ep else "│   ├── " if not is_last_season else "    ├── "
            if is_last_season:
                ep_prefix = "    └── " if is_last_ep else "    ├── "
            tree_lines.append(f"{ep_prefix}{episode}")
    
    return "\n".join(tree_lines)


def organize_files(structure: dict, source_base: str, dest_base: str, dry_run: bool = True) -> bool:
    """Organize files according to structure"""
    series_name = structure['series_name']
    year = structure['year']
    folder_name = f"{series_name} ({year})" if year else series_name
    
    series_path = Path(dest_base) / folder_name
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Organizing files...")
    
    moved_count = 0
    for ep in structure['episodes']:
        season_num = ep['season']
        season_folder = series_path / f"Season {season_num:02d}"
        
        # Find source file
        source_file = Path(source_base) / ep['original_filename']
        if not source_file.exists():
            print(f"⚠️  Warning: Source file not found: {source_file}")
            continue
        
        dest_file = season_folder / ep['new_filename']
        
        if not dry_run:
            season_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_file), str(dest_file))
            print(f"✓ Moved: {ep['original_filename']} -> {ep['new_filename']}")
        else:
            print(f"  Would move: {ep['original_filename']} -> {season_folder.name}/{ep['new_filename']}")
        
        moved_count += 1
        
        # Move related files with same name but different extensions (e.g., .nfo, .srt, .sub)
        source_stem = source_file.stem  # filename without extension
        source_parent = source_file.parent
        dest_stem = dest_file.stem
        
        # Find all files with same name but different extension
        for related_file in source_parent.glob(f"{source_stem}.*"):
            if related_file == source_file:
                continue  # Skip the main video file we already moved
            
            # Get the extension and create destination path
            extension = related_file.suffix
            related_dest = season_folder / f"{dest_stem}{extension}"
            
            if not dry_run:
                shutil.move(str(related_file), str(related_dest))
                print(f"  ✓ Also moved: {related_file.name} -> {related_dest.name}")
            else:
                print(f"    Would also move: {related_file.name} -> {related_dest.name}")
            
            moved_count += 1
    
    print(f"\n{'Would move' if dry_run else 'Moved'} {moved_count} files")
    return True


def process_folder(api_key: str, source_folder: str, tv_unordered_base: str, tv_base: str):
    """Process a single folder from tv_unordered"""
    
    print(f"\n{'='*70}")
    print(f"Processing: {source_folder}")
    print(f"{'='*70}\n")
    
    # Get directory tree
    folder_path = Path(tv_unordered_base) / source_folder
    tree = get_directory_tree(str(folder_path))
    
    print("Directory structure:")
    print(tree)
    print()
    
    # Call LLM
    print("Analyzing with DeepSeek LLM...")
    structure = call_deepseek_api(api_key, tree, source_folder)
    
    print(f"\n✓ Detected series: {structure['series_name']}")
    if structure['year']:
        print(f"✓ Year: {structure['year']}")
    print(f"✓ Episodes found: {len(structure['episodes'])}")
    
    # Generate preview
    print(f"\n{'='*70}")
    print("PREVIEW: New structure")
    print(f"{'='*70}\n")
    preview = generate_preview_tree(structure, tv_base)
    print(preview)
    
    # Ask for confirmation
    print(f"\n{'='*70}")
    response = input("\nApply this organization? (y/n): ").strip().lower()
    
    if response == 'y':
        organize_files(structure, str(folder_path), tv_base, dry_run=False)
        print("\n✓ Organization complete!")
        return True
    else:
        print("\n✗ Organization cancelled")
        return False


def main():
    """Main entry point"""
    
    # Configuration
    WORKSPACE = Path(__file__).parent
    TV_UNORDERED = WORKSPACE / "tv_unordered"
    TV = WORKSPACE / "tv"
    
    print("TV Series Organizer with DeepSeek LLM")
    print("=" * 70)
    
    # Get API key
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        api_key = input("Enter your DeepSeek API key: ").strip()
    
    if not api_key:
        print("Error: API key is required")
        return
    
    # Check directories
    if not TV_UNORDERED.exists():
        print(f"Error: {TV_UNORDERED} does not exist")
        return
    
    TV.mkdir(exist_ok=True)
    
    # Get folders to process
    folders = [f.name for f in TV_UNORDERED.iterdir() if f.is_dir()]
    
    if not folders:
        print(f"No folders found in {TV_UNORDERED}")
        return
    
    print(f"\nFound {len(folders)} folder(s) to process:")
    for i, folder in enumerate(folders, 1):
        print(f"  {i}. {folder}")
    
    print("\nOptions:")
    print("  - Enter folder number to process specific folder")
    print("  - Enter 'all' to process all folders")
    print("  - Enter 'q' to quit")
    
    choice = input("\nYour choice: ").strip().lower()
    
    if choice == 'q':
        return
    elif choice == 'all':
        for folder in folders:
            process_folder(api_key, folder, str(TV_UNORDERED), str(TV))
    elif choice.isdigit() and 1 <= int(choice) <= len(folders):
        folder = folders[int(choice) - 1]
        process_folder(api_key, folder, str(TV_UNORDERED), str(TV))
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
