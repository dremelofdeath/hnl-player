#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim:ts=2:sw=2:et:ai

from setuptools import setup

setup(
    name = 'hnlplayer',
    version = '0.11.0',
    license = 'TBD',
    description = "A music player that's on a whole 'nother level.",
    author = 'Zachary Murray',
    author_email = 'dremelofdeath@gmail.com',
    url = 'https://github.com/dremelofdeath/hnl-player',
    packages = ['hnlplayer'],
    setup_requires = [
      "pytest-runner"
    ],
    install_requires = [
      'PyQt5>=5.12.1',
      'mutagen>=1.28',
      'euphonogenizer>=1.0',
    ],
    tests_require = [
      "pytest"
    ],
    entry_points = {
      'gui_scripts': [
        'hnl = hnlplayer.hnl:main',
      ],
    },
)

