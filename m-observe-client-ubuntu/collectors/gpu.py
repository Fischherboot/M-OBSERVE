"""GPU telemetry collector (NVIDIA via pynvml)."""
import logging

log = logging.getLogger("m-observe")

_nvml_available = False
try:
    import pynvml
    pynvml.nvmlInit()
    _nvml_available = True
except Exception:
    pass


def collect() -> dict:
    gpus = []
    if not _nvml_available:
        return {"gpus": gpus}
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()
            gpu = {"name": name}
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                gpu["usage_percent"] = util.gpu
                gpu["encoder_percent"] = 0
                gpu["decoder_percent"] = 0
            except Exception:
                pass
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                gpu["vram_used_mb"] = round(mem.used / (1024 * 1024))
                gpu["vram_total_mb"] = round(mem.total / (1024 * 1024))
            except Exception:
                pass
            try:
                gpu["temp_c"] = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                pass
            try:
                gpu["power_draw_w"] = round(pynvml.nvmlDeviceGetPowerUsage(h) / 1000)
            except Exception:
                pass
            try:
                gpu["power_limit_w"] = round(pynvml.nvmlDeviceGetEnforcedPowerLimit(h) / 1000)
            except Exception:
                pass
            try:
                gpu["fan_speed_percent"] = pynvml.nvmlDeviceGetFanSpeed(h)
            except Exception:
                pass
            try:
                driver = pynvml.nvmlSystemGetDriverVersion()
                if isinstance(driver, bytes):
                    driver = driver.decode()
                gpu["driver"] = driver
            except Exception:
                pass
            try:
                cuda = pynvml.nvmlSystemGetCudaDriverVersion_v2()
                gpu["cuda_version"] = f"{cuda // 1000}.{(cuda % 1000) // 10}"
            except Exception:
                pass
            try:
                pcie_gen = pynvml.nvmlDeviceGetCurrPcieLinkGeneration(h)
                pcie_width = pynvml.nvmlDeviceGetCurrPcieLinkWidth(h)
                gpu["pcie_gen"] = pcie_gen
                gpu["pcie_width"] = pcie_width
            except Exception:
                pass
            gpus.append(gpu)
    except Exception as e:
        log.debug(f"GPU collect error: {e}")
    return {"gpus": gpus}
