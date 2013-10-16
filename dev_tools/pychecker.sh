#!/bin/sh

check_for_command () {
    if ! type $1 > /dev/null; then
	echo "The pychecker script requires that the $1 command is installed"
	echo "Exiting!"
	exit 10
    fi
}

check_for_command "pep8"
check_for_command "pyflakes"
check_for_command "pylint"

pep8 $1
pyflakes $1
pylint --reports=n --output-format=parseable --disable=I0011 $1
