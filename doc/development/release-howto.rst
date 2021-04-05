Release Procedures
==================

This document describes the necessary steps for creating a new release of SoCo.


Preparations
------------

* Verify the version number stated in the release ticket (according to
  `semantic versioning <http://semver.org/>`_. Tag names should be prefixed
  with ``v``.

* Create the release notes RST document in ``doc/releases`` by copying
  contents from the release notes issue. Texts can be rewritten for
  legibility.

* Verify that all tests pass locally and on all supported versions of
  Python via Travis-CI (the status is visible on the project frontpage
  on GitHub).


Create and Publish
------------------

* Update the version number in ``__init__.py`` (see `example
  <https://github.com/SoCo/SoCo/commit/d35171213eabbc4>`_) and commit.

* (**If any changes other than the version number was made** in
  preparation for the release, push the release commit to GitHub
  before proceeding, to ensure that all the continuous integration
  passes. The automatic deployment to PyPI mentioned below, will not
  work if continuous integration fails.)

* Tag the current commit, eg

.. code-block:: bash

    git tag -a v0.7 -m 'release version 0.7'

* Push the tag. This will create a new release on GitHub, and will
  automatically deploy the new version to PyPI (see `#593
  <https://github.com/SoCo/SoCo/pull/593>`_)

.. code-block:: bash

    git push --tags

* Update the `GitHub release <https://github.com/SoCo/SoCo/releases/new>`_
  using the release notes from the documentation. The release notes can be
  abbreviated if a link to the documentation is provided.


Wrap-Up
-------

* Close the milestone and issues for the release.

* Update the version number in ``__init__.py`` with an added "+" to
  indicate development status (see `example
  <https://github.com/SoCo/SoCo/commit/2bf8caf7736772920bafd1
  81d8b844269d95be17>`__).

* Share the news!


Preparation for next release
----------------------------

* Define the next version number and expected release date (3 month after the
  current release date, as per `#524
  <https://github.com/SoCo/SoCo/issues/524>`_)).

* Create the milestone and set the release date.

* Create an issue for the upcoming release (tagged as `Release
  <https://github.com/SoCo/SoCo/issues?q=is%3Aissue+is%3Aopen+label%3ARelease>`_),
  and one for the corresponding release notes.
