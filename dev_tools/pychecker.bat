echo off
echo ======  pep8  ======
C:\Users\ken\pythonchecks\pep8.py %1

echo ======  pylint  ======
pylint --disable=I0011 --report=n --output-format=parseable %1
