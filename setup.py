from setuptools import setup


setup(
    name='pgspawn',
    version='0.1.0',
    description='Spawn graph of processes that communicate with each other via UNIX pipes',
    license='MIT',
    url='https://github.com/SupraSummus/pgspawn',
    classifiers=[
        'Operating System :: POSIX',
        'Topic :: System',
        'Topic :: Utilities',
    ],
    keywords='unix pipe graph command',
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
