"""Network telemetry collector."""
import psutil


def collect() -> dict:
    interfaces = []
    addrs = psutil.net_if_addrs()
    counters = psutil.net_io_counters(pernic=True)
    for name, addr_list in addrs.items():
        if name == "lo":
            continue
        ip = None
        for a in addr_list:
            if a.family.name == "AF_INET":
                ip = a.address
                break
        if ip is None:
            continue
        c = counters.get(name)
        interfaces.append({
            "name": name,
            "ip": ip,
            "rx_bytes": c.bytes_recv if c else 0,
            "tx_bytes": c.bytes_sent if c else 0,
        })
    return {"network": {"interfaces": interfaces}}
