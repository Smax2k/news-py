import os
import atexit

PROCESS_LOCK = 'process.lock'
MAIN_LOCK = 'main.lock'

class LockError(Exception):
    pass

def create_lock(lock_file):
    """Crée un fichier de verrou"""
    with open(lock_file, 'w') as f:
        f.write('1')

def remove_lock(lock_file):
    """Supprime un fichier de verrou"""
    if os.path.exists(lock_file):
        os.remove(lock_file)

def is_locked(lock_file):
    """Vérifie si un verrou existe"""
    return os.path.exists(lock_file)

def file_lock(lock_type="process"):
    """Context manager pour le verrouillage de fichier"""
    class LockContext:
        def __init__(self, lock_type):
            self.lock_file = PROCESS_LOCK if lock_type == "process" else MAIN_LOCK
            self.other_lock = MAIN_LOCK if lock_type == "process" else PROCESS_LOCK

        def __enter__(self):
            if is_locked(self.lock_file) or is_locked(self.other_lock):
                raise LockError("Un autre processus est en cours d'exécution")
            create_lock(self.lock_file)
            atexit.register(lambda: remove_lock(self.lock_file))
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            remove_lock(self.lock_file)

    return LockContext(lock_type)

def is_main_running():
    """Vérifie si main.py est en cours d'exécution"""
    return is_locked(MAIN_LOCK)

def is_cleaning_running():
    """Vérifie si le nettoyage est en cours d'exécution"""
    return is_locked(PROCESS_LOCK)
