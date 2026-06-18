import os

def search_local_files(directory: str, keyword: str):
    matches = []
    files_checked = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if files_checked > 100:
                return {
                    "directory": directory,
                    "keyword": keyword,
                    "matches": matches
                    }
            files_checked +=1
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding='utf-8') as f:
                    for line_num, line in enumerate(f, start=1):
                        clean_line = line.strip()
                        if keyword.lower() in clean_line.lower():
                            matches.append(f"{file_path}: {line_num}: {clean_line}")
            except (UnicodeDecodeError, PermissionError) as e:
                continue
    return {
        "directory": directory,
        "keyword": keyword,
        "matches": matches
    }
    
def list_directory_contents(directory: str):
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