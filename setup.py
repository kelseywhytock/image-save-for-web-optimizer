from setuptools import setup

APP = ["image_optimizer.py"]
DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "AppIcon.icns",
    "plist": {
        "CFBundleName": "Image Optimizer",
        "CFBundleDisplayName": "Image Optimizer",
        "CFBundleIdentifier": "com.kelseywhytock.image-optimizer",
        "CFBundleVersion": "1.1.1",
        "CFBundleShortVersionString": "1.1",
        "NSHighResolutionCapable": True,
        # Drop target — accept image files
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Image",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "CFBundleTypeExtensions": [
                    "jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp"
                ],
            }
        ],
        # Only declare Documents for the output folder — Desktop/Downloads access
        # is granted implicitly when the user drops files from those locations.
        # Declaring them here causes macOS to prompt on every launch regardless
        # of whether those folders are actually used.
        "NSDocumentsFolderUsageDescription": "Image Optimizer needs access to your Documents folder to save optimized images.",
    },
    "packages": ["PIL"],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
