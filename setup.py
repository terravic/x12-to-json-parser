from setuptools import setup, find_packages

setup(
    name="x12-to-json-parser",
    version="1.0.0",
    description="Enterprise EDI X12 (5010) to structured JSON parser with C-CDA XML clinical integration.",
    author="Healthcare Interoperability Engineering",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "x12-parser=x12_parser.cli:main",
            "x12-server=x12_parser.api.server:run_server",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
