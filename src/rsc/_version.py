import sys
from importlib.metadata import version, PackageNotFoundError


def _user_agent() -> str:
    try:
        pkg_version = version("rsc-client")
    except PackageNotFoundError:
        pkg_version = "unknown"
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return f"rsc-python-client/{pkg_version} Python/{py_version}"
