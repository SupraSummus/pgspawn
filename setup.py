from setuptools import setup


setup(
    name='pgspawn',
    version='1.0',
    py_modules=['pgspawn'],
    scripts=['scripts/pgspawn', 'scripts/pg2dot'],
    install_requires=[
        'PyYAML',
        'graphviz==0.8.*',
    ],
)
