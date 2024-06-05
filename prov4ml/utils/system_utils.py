
import psutil
import torch
import sys
if sys.platform != 'darwin':
    import pyamdgpuinfo
    import GPUtil
else: 
    import apple_gpu


def get_cpu_usage() -> float:
    """
    Returns the current CPU usage percentage.
    
    Returns:
        float: The CPU usage percentage.
    """
    return psutil.cpu_percent()

def get_memory_usage() -> float:
    """
    Returns the current memory usage percentage.
    
    Returns:
        float: The memory usage percentage.
    """
    return psutil.virtual_memory().percent

def get_disk_usage() -> float:
    """
    Returns the current disk usage percentage.
    
    Returns:
        float: The disk usage percentage.
    """
    return psutil.disk_usage('/').percent

def get_gpu_memory_usage() -> float:
    """
    Returns the current GPU memory usage percentage, if GPU is available.
    
    Returns:
        float: The GPU memory usage percentage.
    """
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / torch.cuda.memory_reserved()
    else:
        return 0
    
def get_gpu_power_usage() -> float:
    """
    Returns the current GPU power usage percentage, if GPU is available.
    
    Returns:
        float: The GPU power usage percentage.
    """
    if sys.platform != 'darwin':
        gpu_power = 0.0
        if torch.cuda.is_available():
            current_gpu = torch.cuda.current_device()
            gpus = GPUtil.getGPUs()
            if current_gpu < len(gpus) and hasattr(gpus[current_gpu], 'power'):
                gpu_power = gpus[current_gpu].power
            else:
                gpu_power = 0.0

            if gpu_power is None or gpu_power == 0.0:
                # n_devices = pyamdgpuinfo.detect_gpus()
                first_gpu = pyamdgpuinfo.get_gpu(0) # returns a GPUInfo object
                gpu_power = first_gpu.query_power()
    else:
        statistics = apple_gpu.accelerator_performance_statistics()
        if 'Power Usage' in statistics.keys():
            gpu_power = statistics['Power Usage']
        else:
            gpu_power = 0.0

    return gpu_power
    

def get_gpu_temperature() -> float:
    """
    Returns the current GPU temperature, if GPU is available.
    
    Returns:
        float: The GPU temperature.
    """
    if sys.platform != 'darwin':
        gpu_temperature = 0.0
        if torch.cuda.is_available():
            current_gpu = torch.cuda.current_device()
            gpus = GPUtil.getGPUs()
            if current_gpu < len(gpus) and hasattr(gpus[current_gpu], 'temperature'):
                gpu_temperature = gpus[current_gpu].temperature
            else:
                gpu_temperature = 0.0

            if gpu_temperature is None or gpu_temperature == 0.0:
                # n_devices = pyamdgpuinfo.detect_gpus()
                first_gpu = pyamdgpuinfo.get_gpu(0)
                gpu_temperature = first_gpu.query_temperature()
    else:
        statistics = apple_gpu.accelerator_performance_statistics()
        if 'Temperature' in statistics.keys():
            gpu_temperature = statistics['Temperature']
        else:
            gpu_temperature = 0.0

    return gpu_temperature

def get_gpu_usage() -> float:
    """
    Returns the current GPU usage percentage, if GPU is available.
    
    Returns:
        float: The GPU usage percentage.
    """
    if sys.platform != 'darwin':
        gpu_utilization = 0.0
        if torch.cuda.is_available():
            current_gpu = torch.cuda.current_device()
            gpus = GPUtil.getGPUs()
            if current_gpu < len(gpus) and hasattr(gpus[current_gpu], 'load'):
                gpu_utilization = gpus[current_gpu].load
            else:
                gpu_utilization = 0.0

            if gpu_utilization is None or gpu_utilization == 0.0:
                # n_devices = pyamdgpuinfo.detect_gpus()
                first_gpu = pyamdgpuinfo.get_gpu(0)
                gpu_utilization = first_gpu.query_load()
    else:
        statistics = apple_gpu.accelerator_performance_statistics()
        if 'Device Utilization' in statistics.keys():
            gpu_utilization = statistics['Device Utilization']
        else:
            gpu_utilization = 0.0

    return gpu_utilization