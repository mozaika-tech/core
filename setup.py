"""Setup configuration for the mozaika-core package."""

from setuptools import setup, find_packages

setup(
    name="mozaika-core",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.13",
    install_requires=[
        # Dependencies are managed in requirements.txt
    ],
)