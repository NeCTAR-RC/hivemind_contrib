import email

from fabric.api import hide
from fabric.api import run


def get_package(package):
    with hide("everything"):
        res = run(f"dpkg -s {package}")
    return email.message_from_string(res)


def current_version(package):
    package = get_package(package)
    if package["Status"] == "install ok installed":
        return package["Version"]


def current_versions(package):
    if isinstance(package, list):
        package = " ".join(package)
    with hide("everything"):
        res = run(f"dpkg -l {package}")
    return res
