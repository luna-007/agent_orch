import shutil

def get_disk_usage():
    storage_space = shutil.disk_usage("/")
    storage = {
        "total" : f"{round(storage_space.total/1024**3, ndigits=2)} Gb",
        "used" : f"{round(storage_space.used/1024**3, ndigits=2)} Gb",
        "free" : f"{round(storage_space.free/1024**3, ndigits=2)} Gb"
    }
    return storage
