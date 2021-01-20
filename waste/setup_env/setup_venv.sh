#!/bin/sh

OS_PYTHON=/usr/local/bin/python3.8
VENV_DIR=.venv3

if [ "$1" = "--clean" ]
then
    rm -rf $VENV_DIR
fi

if [ ! -d $VENV_DIR ] 
then
    $OS_PYTHON -m venv $VENV_DIR
fi

source $VENV_DIR/bin/activate

# The next line uses 'python' not '$OS_PYTHON' so that it picks
# up the activated venv python not the base OS version
python -m pip install --upgrade pip rope wheel coverage pytest
python -m pip install boto3 ifaddr requests
