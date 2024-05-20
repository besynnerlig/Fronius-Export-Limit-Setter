# Fronius Export Limit Setter

This script sets the soft export limit field on a Fronius inverter. It has been tested on a Fronius Symo 15.0-3-M.

## Features

- Sets the export limit on a Fronius inverter.
- Outputs results in JSON format.
- Option to run in debug mode, capturing screenshots on errors.
- Can be run in headless or non-headless mode.

## Setup Instructions

1. **Fronius Inverter Configuration**:
   - Ensure you have the service password for your Fronius inverter.
   - In the DNO Editor, scroll down to "Dynamic power reduction" and ensure that "Limit Entire System" and "Export Limiting Control (Soft Limit)" are both selected.

## Script Arguments

The script requires the following arguments:

- `-d`, `--debug`: Enable debug mode. Captures a screenshot if an exception occurs.
- `-f`, `--fronius_url`: The URL of your Fronius inverter (e.g., `http://192.168.2.100`).
- `-p`, `--fronius_password`: The password to access your Fronius inverter.
- `-e`, `--export_limit`: The desired export limit in Watts.
- `-n`, `--not_headless`: Disable headless mode in Firefox. Useful for debugging.

## Script Output

The script outputs JSON data. An example output looks like this:

```json
{
  "desired_limit": 15123,
  "status": "success",
  "message": "Limit successfully updated.",
  "current_limit": "15100",
  "new_limit": "15123"
}

## Running the Script Locally

1. **Install Dependencies**:
   - Ensure Python and Firefox are installed.
   - Create a virtual environment (optional but recommended):
     ```sh
     python -m venv venv
     ```
   - Activate the virtual environment:
     ```sh
     . venv/bin/activate  # On Linux
     ```
   - Install the required Python packages:
     ```sh
     pip install -r requirements.txt
     ```

2. **Run the Script**:
   ```sh
   ./main.py -e 15000 -f http://fronius -p "R3D@CT3D"


## Running the Script in Docker

1. **Ensure Docker is Installed**:
   - Follow the [official Docker installation guide](https://docs.docker.com/get-docker/).

2. **Run the Docker Container**:
   ```sh
   docker run --rm besynnerlig/fronius-export-limit-setter -e 15000 -f http://fronius -p "R3D@CT3D"

## Handling Errors

If an exception is thrown during execution and the script is running in debug mode, the script will output a base64 representation of a screenshot to the terminal. You can convert this screenshot using an online base64 to image converter to gain insights into the error.

## Liability and Warranty

This software comes with no warranty and no support. Use it at your own risk. The author shall not be held liable nor be blamed for any damages that occur directly or indirectly from using it.

## Project Origin and License

This script is derived from the original work by shadow7412 on GitHub:
[Original Script](https://github.com/shadow7412/fronius-driver/blob/master/main.py)

The original script was designed for Home Assistant integration and released under the GPL-3.0 license. This modified version generalizes the functionality to be used independently of any specific home automation system.

**License**: GPL-3.0

This updated script can be found at: [Fronius Export Limit Setter](https://github.com/besynnerlig/Fronius-Export-Limit-Setter)
