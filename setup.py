from setuptools import setup


setup(
    name='pgspawn',
    version='1.0',
    py_modules=['pgspawn'],
    scripts=['scripts/pgspawn'],
    install_requires=[
        'PyYAML',
    ],
)
