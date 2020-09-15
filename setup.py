from setuptools import setup

setup(
    name='logger',
    version='0.93',
    summary='Sane logging for python in Kubernetes',
    packages=['logger'],
    install_requires=['sanic>20.6'],
    python_requires='>=3.8'
)
