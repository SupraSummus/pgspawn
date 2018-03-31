from setuptools import setup


setup(
    name='pgspawn',
    version='1.0',
    py_modules=['pgspawn'],
    scripts=[
        'pgspawn',
        'pg2dot',
    ],
    install_requires=[
        'PyYAML',
        'graphviz==0.8.*',
    ],
)
