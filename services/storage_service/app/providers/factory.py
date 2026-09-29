from .nextcloud_provider import NextcloudProvider
from .onedrive_provider import OneDriveProvider
from .sharepoint_provider import SharePointProvider


def get_provider(provider: str):
    provider = provider.lower().strip()

    if provider == "onedrive":
        return OneDriveProvider()

    if provider == "sharepoint":
        return SharePointProvider()

    if provider == "nextcloud":
        return NextcloudProvider()

    raise ValueError("Unsupported provider. Use one of: onedrive, sharepoint, nextcloud")
