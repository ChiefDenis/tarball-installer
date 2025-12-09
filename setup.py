from setuptools import setup, find_packages
import os

# Read requirements from file
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name="tarball-installer",
    version="1.0.0",
    author="Chief Denis",
    author_email="your.email@example.com",
    description="Install tarballs as native applications",
    long_description=open('README.md').read() if os.path.exists('README.md') else "",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=requirements,
    entry_points={
        "gui_scripts": [
            "tarball-installer=tarball_installer.main:main",
        ],
    },
    data_files=[
        ("share/applications", ["data/com.chiefdenis.tarballinstaller.desktop"]),
        ("share/metainfo", ["data/com.chiefdenis.tarballinstaller.appdata.xml"]),
        ("share/icons/hicolor/scalable/apps", ["data/icons/com.chiefdenis.tarballinstaller.svg"]),
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Topic :: System :: Installation/Setup",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
)