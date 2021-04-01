Unit and integration tests
**************************

There are two sorts of tests written for the ``SoCo`` package. Unit tests
implement elementary checks of whether the individual methods produce the
expected results. Integration tests check that the package as a whole is able to
interface properly with the Sonos hardware. Such tests are especially useful
during re-factoring and to check that already implemented functionality
continues to work past updates to the Sonos units' internal software.

Setting up your environment
===========================

To run the unit tests, you will need to have the `pytest <http://pytest.org/latest>`_
testing tool installed.

You can install them and other development dependencies using the
:file:`requirements-dev.txt` file like this:

.. code-block:: sh

	pip install -r requirements-dev.txt

Running the unit tests
======================

There are different ways of running the unit tests. The easiest is to use ``py.test's`` automatic test discovery.  Just change to the root directory of the ``SoCo`` package and type:

.. code-block:: sh

	py.test

For others, see the `py.test documentation <http://pytest.org/latest/usage.html>`_

.. note:: To run the unittests in this way, the soco package must be
   importable, i.e. the folder that contains it (the root folder of
   the git archive) must be in the list of paths that Python can
   import from (the PYTHONPATH). The easiest way to set this up, if
   you are using a virtual environment, is to install SoCo from the
   git archive in editable mode. This is done by executing the
   following command from the git archive root:

   .. code-block:: sh

      pip install -e .


Running the integration tests
=============================

At the moment, the integration tests cannot be run under the control of ``py.test``. To run them, enter the ``unittest`` folder in the source code
checkout and run the test execution script
``execute_unittests.py`` (it is required that the *SoCo* checkout is
added to the Python path of your system). To run all the unit tests
for the *SoCo* class execute the following command:

.. code-block:: sh

    python execute_unittests.py --modules soco --ip 192.168.0.110

where the IP address should be replaced with the IP address of the
Sonos® unit you want to use for the unit tests (NOTE! At present the
unit tests for the *SoCo* module requires your Sonos® unit to be playing
local network music library tracks from the queue and have at least
two such tracks in the queue). You can get a list of all the units in
your network and their IP addresses by running:

.. code-block:: sh

    python execute_unittests.py --list

To get the help for the unit test execution script which contains a
description of all the options run:

.. code-block:: sh

    python execute_unittests.py --help

Unit test code structure and naming conventions
===============================================

The unit tests for the *SoCo* code should be organized according to
the following guidelines.

.. _section_one_module_per_class:

One unit test module per class under test
-----------------------------------------

Unit tests should be organized into modules, one module, i.e. one
file, for each class that should be tested. The module should be named
similarly to the class except replacing CamelCase with underscores and
followed by ``_unittest.py``.

Example: Unit tests for the class ``FooBar`` should be stored in
``foo_bar_unittests.py``.

.. _section_one_class_per_method:

One unit test class per method under test
-----------------------------------------

Inside the unit test modules the unit test should be organized into
one unit test case class per method under test. In order for the test
execution script to be able to calculate the test coverage, the test
classes should be named the same as the methods under test except that
the lower case underscores should be converted to CamelCase. If the
method is private, i.e. prefixed with 1 or 2 underscores, the test
case class name should be prefixed with the word ``Private``.

Examples:

==========================  =========================
Name of method under test   Name of test case class
==========================  =========================
``get_current_track_info``  ``GetCurrentTrackInfo``
``__parse_error``           ``PrivateParseError``
``_my_hidden_method``       ``PrivateMyHiddenMethod``
==========================  =========================

.. _section_add_unit_test:

Add an unit test to an existing unit test module
================================================

To add a unit test case to an existing unit test module ``Foo`` first check
with the following command which methods that does not yet have unit tests:

.. code-block:: sh

    python execute_unittests.py --modules foo --coverage

After having identified a method to write a unit test for, consider
what criteria should be tested, e.g. if the method executes and
returns the expected output on valid input and if it fails as expected on
invalid input. Then implement the unit test by writing a
class for it, following the naming convention mentioned in section
:ref:`section_one_class_per_method`. You can read more about unit test
classes in the `reference documentation
<http://docs.python.org/2/library/unittest.html>`_ and there is a good
introduction to unit testing in `Mark Pilgrim's "Dive into Python"
<http://www.diveintopython.net/unit_testing/index.html>`_ (though the
aspects of test driven development, that it describes, is not a
requirement for *SoCo* development).

Special unit test design consideration for *SoCo*
-------------------------------------------------

*SoCo* is developed purely by volunteers in their spare time. This
leads to some special consideration during unit test design.

First of, volunteers will usually not have extra Sonos® units
dedicated for testing. For this reason the unit tests should be developed
in such a way that they can be run on units in use and with people
around, so e.g it should be avoided settings the volume to max.

Second, being developed in peoples spare time, the development is
likely a recreational activity, that might just be accompanied by
music from the same unit that should be tested. For this reason, that
unit should be left in the same state after test as it was
before. That means that the play list, play state, sound settings
etc. should be restored after the testing is complete.

Add a new unit test module (for a new class under test)
=======================================================

To add unit tests for the methods in a new class follow the steps below:

1. Make a new file in the unit test folder named as mentioned in
   section :ref:`section_one_module_per_class`.
2. (Optional) Define an ``init`` function in the unit test module. Do
   this only if it is necessary to pass information to the tests at
   run time. Read more about the ``init`` function in the section
   :ref:`section_init_function`.
3. Add test case classes to this module. See :ref:`section_add_unit_test`.

Then it is necessary to make the unit test execution framework aware of
your unit test module. Do this by making the following additions to
the file ``execute_unittests.py``.:

1. Import the class under test and the unit test module in the
   beginning of the file
2. Add an item to the ``UNITTEST_MODULES`` dict located right after the
   ``### MAIN SCRIPT`` comment. The added item should itself be a
   dictionary with items like this::

    UNITTEST_MODULES = {
     'soco': {'name': 'SoCo', 'unittest_module': soco_unittest,
              'class': soco.SoCo, 'arguments': {'ip': ARGS.ip}},
     'foo_bar': {'name': 'FooBar', 'unittest_module': foo_bar_unittest,
                'class': soco.FooBar,'arguments': {'ip': ARGS.ip}}
     }

   where both the new imaginary ``foo_bar`` entry and the existing
   ``soco`` entry are shown for clarity. The arguments dict is what will be
   passed on to the ``init`` method, see section
   :ref:`section_init_function`.
3. Lastly, add the new module to the help text for the ``modules``
   command line argument, defined in the ``__build_option_parser``
   function::

    parser.add_argument('--modules', type=str, default=None, help=''
                        'the modules to run unit test for can be '
                        '\'soco\', \'foo_bar\' or \'all\'')

   The name that should be added to the text is the key for the unit
   test module entry in the ``UNITTEST_MODULES`` dict.

.. _section_init_function:

The ``init`` function
---------------------

Normally unit tests should be self-contained and therefore they should
have all the data they will need built in. However, that does not
apply to *SoCo*, because the IP's of the Sonos® units will be required
and there is no way to know them in advance. Therefore, the execution
script will call the function ``init`` in the unit test modules, if it
exists, with a set of predefined arguments that can then be used for
unit test initialization. Note that the function is to be named
``init`` , not ``__init__`` like the class initializers. The ``init``
function is called with one argument, which is the dictionary defined
under the key ``arguments`` in the unit test modules definition. Please
regard this as an exception to the general unit test best practices
guidelines and use it only if there are no other option.
