from setuptools import setup, find_packages
import os

# Read dependencies from requirements.txt, removing BOM if present
with open("requirements.txt", encoding="utf-8-sig") as f:
    requirements = [line.strip() for line in f if line.strip()]

# Read long description from README.md if it exists
long_description = ""
if os.path.exists("README.md"):
    with open("README.md", encoding="utf-8") as f:
        long_description = f.read()

setup(
    name="CreateValidationHANA",            # Project name
    version="1.0.0",                     # Project version
    author="Michael J. Ocasio",
    author_email="mjo23@live.com",
    description="A Python tool to identify and validate discrepancies unicode " \
    "value not corrected translated by the data source",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/HHS/OAPS-ETL/tree/ReportValidationHana",  # Optional project URL
    packages=find_packages(),            # Automatically find packages in your project
    include_package_data=True,           # Include non-Python files (like Excel templates)
    install_requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires='>=3.13.1',          # Minimum Python version
)
