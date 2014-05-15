
lint: soco
	flake8 soco
	pylint --disable=I0011 --rcfile=.pylintrc soco

.PHONY: lint
