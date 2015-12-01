===============================
Hivemind Contrib
===============================

A collection of hivemind tasks.

* Free software: GPLv2 License

Install on Ubuntu 14.04.2 LTS
-----------------------------

Hivemind contrib requires you first install hivemind.

You need the following packages ::

  sudo apt-get install libmariadbclient-dev libssl-dev python-virtualenv

And then you will need to install some python dependencies ::

  sudo pip install pyopenssl ndg-httpsclient pyasn1

You probably want a source install so run ::

  git clone git@github.com:NeCTAR-RC/hivemind_contrib.git
  cd hivemind_contrib
  virtualenv venv
  . venv/bin/activate
  pip install -e .

Features
--------

* TODO
