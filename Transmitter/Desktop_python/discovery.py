"""Local-network discovery for TV receiver endpoints."""

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib.request import urlopen


RECEIVER_PORT = 8080
DISCOVERY_TIMEOUT_SECONDS = 0.35
DISCOVERY_WORKERS = 48


def _local_network() -> ipaddress.IPv4Network:
    """Return the /24 network used by the active network connection."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        # Connecting a UDP socket sends no traffic; it only lets Windows choose
        # the network interface that would reach an external host.
        probe.connect(("8.8.8.8", 80))
        local_ip = probe.getsockname()[0]
    return ipaddress.ip_network(f"{local_ip}/24", strict=False)


def _is_receiver(address: str) -> bool:
    """Check whether an address is running this app's TV receiver."""
    try:
        with urlopen(
            f"http://{address}:{RECEIVER_PORT}/", timeout=DISCOVERY_TIMEOUT_SECONDS
        ) as response:
            return 200 <= response.status < 500
    except (OSError, URLError, TimeoutError):
        return False


def discover_receivers() -> list[str]:
    """Find reachable TV receiver endpoints on the active local subnet."""
    network = _local_network()
    addresses = (str(host) for host in network.hosts())
    with ThreadPoolExecutor(max_workers=DISCOVERY_WORKERS) as executor:
        futures = {executor.submit(_is_receiver, address): address for address in addresses}
        return sorted(
            futures[future] for future in as_completed(futures) if future.result()
        )
