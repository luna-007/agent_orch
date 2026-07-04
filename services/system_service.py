import platform
import psutil
import time

def get_system_info() -> dict:
    """Queries OS release version, CPU core count, dynamic RAM metrics, and system uptime details."""
    svmem = psutil.virtual_memory()
    uptime = time.time() - psutil.boot_time()
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_total_gb": round(svmem.total / (1024 ** 3), 2),
        "memory_available_gb": round(svmem.available / (1024 ** 3), 2),
        "memory_used_percent": svmem.percent,
        "uptime_seconds": round(uptime, 2)
    }
