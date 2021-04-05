.. _getting_started:

Getting started
===============

This section will help you to quickly get started with *SoCo*.

.. _installation:

Installation
------------

*SoCo* can be installed either with :ref:`pip <installation_pip>` (recommended)
or :ref:`manually <installation_manually>`.

.. _installation_pip:

From PyPI with pip
^^^^^^^^^^^^^^^^^^

The easiest way to install *SoCo*, is to install it from `PyPI
<https://pypi.python.org/pypi>`_ with the program `pip
<https://pip.pypa.io/en/stable/>`_. This can be done with the command:

.. code-block:: sh

   pip install soco

This will automatically take care of installing any dependencies you need.

.. _installation_manually:

Manual installation from .tar.gz file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

*SoCo* can also be installed manually from the .tar.gz file. First, find `the
latest version of SoCo on PyPI <https://pypi.python.org/pypi/soco>`_ and
download the ``.tar.gz`` file at the bottom of the page. After that, extract
the content and move into the extracted folder. As an example, for *SoCo*
0.11.1 and on a Unix type system, this can be done with the following commands:

.. code-block:: sh

   wget https://pypi.python.org/packages/source/s/soco/soco-0.11.1.tar.gz#md5=73187104385f04d18ce3e56853be1e0c
   tar zxvf soco-0.11.1.tar.gz
   cd soco-0.11.1/

Have a look inside the ``requirements.txt`` file. You will need to install the
dependencies listed in that file yourself. See the documentation for the
individual dependencies for installation instructions.

After the requirements are in place, the package can be install with the
command:

.. code-block:: sh

   python setup.py install

After installation check
^^^^^^^^^^^^^^^^^^^^^^^^

After installation, open a Python interpreter and check that :mod:`soco` can be
imported and that your Sonos® players can be discovered:

.. code-block:: python

   >>> import soco
   >>> soco.discover()
   set([SoCo("192.168.0.16"), SoCo("192.168.0.17"), SoCo("192.168.0.10")])

.. _tutorial:

Tutorial
--------

*SoCo* allows you to control your Sonos sound system from a Python program. For
a quick start have a look at the `example applications
<https://github.com/SoCo/SoCo/tree/master/examples>`_ that come with the
library.


Discovery
^^^^^^^^^

For discovering the Sonos devices in your network, use :meth:`soco.discover`.

.. code-block:: python

    >>> import soco
    >>> speakers = soco.discover()

It returns a :class:`set` of :class:`soco.SoCo` instances, each representing a
speaker in your network.


Music
^^^^^

You can use those SoCo instances to inspect and interact with your speakers.

.. code-block:: python

    >>> speaker = speakers.pop()
    >>> speaker.player_name
    'Living Room'
    >>> speaker.ip_address
    u'192.168.0.129'

    >>> speaker.volume
    10
    >>> speaker.volume = 15
    >>> speaker.play()


See for :class:`soco.SoCo` for all methods that are available for a speaker.
