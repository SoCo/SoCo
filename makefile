
lint: soco
	flake8 --ignore=E402 soco
	pylint soco

.PHONY: lint
