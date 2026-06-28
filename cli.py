import os, uuid, sys
import questionary
from services.memory_service import MemoryService

def handle_startup_menu(memory_svc: MemoryService) -> tuple[str, list]:
    """Displays the terminal UI session menu and returns (session_id, loaded_messages)"""

    memory_svc.initialize_db()
    
    try:
        sessions = memory_svc.get_sessions()

        print("=== Agent Orch Session Manager ===")
        options = [
            "1. Start a fresh, private session (default)",
            "2. Resume a past session"
        ]
        
        result = questionary.select(
            "Choose an option:",
            choices=options,
            pointer="=>"
        ).ask()
        
        if result == options[0]:
            session_id = str(uuid.uuid4())
            print("\n🚀 Starting a fresh, private session...")
            return (session_id, [])
        elif result == options[1]:
            try:
                session_options = [f"{idx}. {session_name or session_id}" for idx, (session_id, session_name) in enumerate(sessions, start=1)]
                    
                selected_idx = questionary.select(
                    "Choose the session: ",
                    choices=session_options,
                    pointer="=>"
                ).ask()
                
                if selected_idx is None:
                    sys.stdout.write("\n\nSession selection cancelled by user. Exiting!!\n")
                    sys.exit(0)
                
                selected_num = selected_idx.split(".")[0]
                
                selected_idx = int(selected_num) - 1
                session_id = sessions[selected_idx][0]
                
                messages = memory_svc.load_history_from_db(session_id)
                
                print("\n📁 Loading past sessions...")
                return (session_id, messages)
            except (ValueError, IndexError):
                print("\nInvalid choice. Starting a fresh session.")
                session_id = str(uuid.uuid4())
                return (session_id, [])
        else:
            print("\nSession manager cancelled.")      
            return ("", [])  
    except KeyboardInterrupt:
        print("\n\nSession manager closed.")
        sys.exit(0)