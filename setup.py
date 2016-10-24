from setuptools import setup

setup(name='pybash',
      version='0.1.3',
      description='interpreter for python&bash combined',
      author='Pieter-Jan Moreels',
      url='https://github.com/NorthernSec/pybash',
      entry_points={'console_scripts': ['pybash = pybash:main']},
      packages=['pybash'],
      license="Modified BSD license",
)


