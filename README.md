# Fronius driver

This script sets the soft limit field on a fronius inverter.

## Setup

* Ensure you know the service password for your fronius inverter. You will need it.
* In the DNO Editor, scroll down to "Dynamic power reduction", and ensure that "Limit Entire System" and "Export Limiting Control (Soft Limit)" are both selected.

## Script Arguments

The script requires the following arguments:

- `-f`, `--fronius_url`: The URL of your Fronius inverter.
- `-p`, `--fronius_password`: The password to access your Fronius inverter.
- `-e`, `--export_limit`: The desired export limit in Watts

You also have an option to specify whether to run your script in headless mode.

- `-n`, `--not_headless`: Disable the headless mode in Firefox. Potentially useful for debugging. Probably not useful in docker.

## Script output

The script outputs json data. 

Example: `{"desired_limit": 15123, "status": "success", "message": "Limit successfully updated.", "current_limit": "15100", "new_limit": "15123"}`

## How to run the script locally

1. Ensure python and firefox are installed.
2. Create a virtual environment (technically optional, but I'd recommend it) using `python -mvenv venv`
3. Enable it. `. venv/bin/activate` (at least on linux)
4. Install dependencies. `pip install requirements.txt`
5. Run the script with all mandatory arguments.

It might look something like this:

    ./main.py -e 15000 -f http://fronius -p "R3D@CT3D"

## How to run the script in docker

Same deal really, except you get to skip nearly all the steps. Obviously ensure docker is installed though.

    docker run --rm shadowbert/fronius-driver -t ABCDEFG -u http://localhost:8123 -f http://fronius -p "R3D@CT3D"

## What if everything goes belly up?

If an exception is thrown during execution, a base64 representation of a screenshot will be output to the terminal.
Convert it (search for base64 to image in your favourite search engine if you don't know what you're doing) and see if
you gain any insight.