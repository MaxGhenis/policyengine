from setuptools import setup, find_packages
from policyengine import VERSION

setup(
    name="PolicyEngine",
    version=VERSION,
    author="PolicyEngine",
    license="http://www.fsf.org/licensing/licenses/agpl-3.0.html",
    url="https://github.com/policyengine/policyengine",
    install_requires=[
        "OpenFisca-UK==0.10.5",
        "OpenFisca-US==0.24.0",
        "OpenFisca-Tools>=0.1.7",
        "plotly",
        "flask",
        "flask_cors",
        "kaleido",
        "google-cloud-storage>=1.42.0",
        "gunicorn",
        "OpenFisca-Core",
        "microdf_python",
        "numpy",
        "pandas",
        "tables",
        "wheel",
        "rdbl",
        "pytest",
        "dpath>=1.5.0",
    ],
    packages=find_packages(),
)
