import sys
from importlib.metadata import version, PackageNotFoundError

def _rsc_client_version() -> str:
    try:
        return version("rsc-client")
    except PackageNotFoundError:
        return "unknown"


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _user_agent() -> str:
    return f"rsc-python-client/{_rsc_client_version()} Python/{_python_version()}"


def _sdk_headers(product: str = None, product_version: str = None) -> dict:
    """Build the SDK identification headers sent on each GraphQL request.

    With no ``product`` the bare client is unchanged: only ``User-Agent`` is
    sent. When a downstream integration (e.g. ``rubrik-mcp``) supplies a
    ``product``, it is reflected verbatim in ``Sdk-Language``, its version
    (or the ``rsc-client`` version when omitted) in ``Sdk-Version``, and it
    leads the ``User-Agent`` — so RSC can attribute the traffic server-side.
    The consumer owns the exact ``Sdk-Language`` value; ``rsc-client`` adds no
    language suffix.
    """
    if not product:
        return {"User-Agent": _user_agent()}

    # If the product omits its version, fall back to the rsc-client version so
    # the call is still identifiable as coming from the Python client.
    ver = product_version or _rsc_client_version()
    return {
        "Sdk-Language": product,
        "Sdk-Version": ver,
        "User-Agent": (
            f"{product}/{ver} "
            f"(rsc-python-client/{_rsc_client_version()}; Python/{_python_version()})"
        ),
    }
