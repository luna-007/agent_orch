import os

SANDBOX_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _validate_sandbox_path(target_path: str) -> None:
    abs_target = os.path.abspath(target_path)
    
    common = os.path.commonpath([SANDBOX_ROOT, abs_target])
    
    if common != SANDBOX_ROOT:
        raise PermissionError(
            f"Access Denied: Path '{target_path}' attempts to escape the allowed workspace"
        )    

def search_local_files(directory: str, keyword: str):
    _validate_sandbox_path(directory)

    matches = []
    files_checked = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if files_checked > 100:
                return {
                    "directory": directory,
                    "keyword": keyword,
                    "matches": matches,
                    "truncated": True,
                    "message": "Search stopped after 100 files. Narrow the directory to get full results."
                    }
            files_checked +=1
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding='utf-8') as f:
                    for line_num, line in enumerate(f, start=1):
                        clean_line = line.strip()
                        if keyword.lower() in clean_line.lower():
                            matches.append(f"{file_path}: {line_num}: {clean_line}")
            except Exception as e:
                continue
    return {
        "directory": directory,
        "keyword": keyword,
        "matches": matches,
        "truncated": False,
        "message": "Search Complete."
    }
    
def list_directory_contents(directory: str):
    _validate_sandbox_path(directory)

    try:
        directories = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]
        files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
        return {
            "directory": directory,
            "directories": directories,
            "files": files
        }
    except OSError as e:
        return {
            "directory": directory,
            "directories": [],
            "files": [],
            "error": str(e)
        }
        
def resolve_and_validate_path(current_dir: str, target_path: str):
    new_path = os.path.abspath(os.path.join(current_dir, target_path))
    
    _validate_sandbox_path(new_path)
    
    if not os.path.exists(new_path):
        raise FileNotFoundError(f"Path '{target_path}' does not exist.")
    if not os.path.isdir(new_path):
        raise NotADirectoryError(f"Path '{target_path} is not a directory.'")
    return new_path

def read_local_file(current_dir: str, file_path: str) -> dict:
    
    target_path = os.path.abspath(os.path.join(current_dir, file_path))
    
    _validate_sandbox_path(target_path)
    
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"Path: {target_path} does not exist.")
    
    if not os.path.isfile(target_path):
        raise IsADirectoryError(f"Path: {target_path} is a directory, not a file.")
    
    with open(target_path, "r", encoding='utf-8') as f:
        content = f.read()
        
    return {"file_path": target_path, "content": content}