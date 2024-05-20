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

- `-d`, `--debug`: Enable debug mode. Logs messages to both console and to the log file.
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
  "current_limit": 15100,
  "new_limit": 15123
}
```

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
   ./main.py -e 15000 -f http://local_inverter_hostname_or_ip_address -p "R3D@CT3D"

## Handling Errors and logging

Logging is set up to write to a file in a subdirectory called "logs" and ensure this directory is created if it doesn't exist. Additionally, we'll save screenshots as JPG files in the logs directory when an error occurs. More verbose logging and logging to console is made when debug mode is activated.

## OpenHAB HABApp integration example

This script is versatile and can be integrated into various home automation environments. Below is an example of how to call this script from within HABApp in OpenHAB. You will likely need to modify the example code to suit your specific requirements, but it should serve as a useful starting point.

```python
class DynamicPowerReduction(Rule):
    '''Setting the dynamic power reduction on the Fronius inverter'''
    def __init__(self):
        super().__init__()
        self.log = logging.getLogger(f'{configuration["system"]["MY_LOGGER_NAME"]}.{self.rule_name}')
        self.log.setLevel(logging.INFO)
        self.run.soon(self.process_changes)
        self.run.soon(self.new_export_limit)
        energy_price_sell_item.listen_event(self.process_changes, ValueChangeEventFilter())
        grid_export_limit_item.listen_event(self.new_export_limit, ValueChangeEventFilter())

    def _on_subprocess_finished(self, process_output: str):
        #self.log.debug(process_output)
        try:
            # Parse the JSON response
            response_data = json.loads(process_output)
        except Exception as e:
            self.log.error(f"Failed to convert the response from the Fronius grid export limit script with error: {e}")
            self.log.error(process_output)
            return

        # Check the status and log the appropriate message
        status = response_data.get('status', 'unknown')
        if status == 'success':
            self.log.info(f"New export limit value: {response_data['new_limit']} successfully set")
        elif status == 'skipped':
            self.log.info(f"Current limit [{response_data['new_limit']}] matches desired limit. Skipping update.")
        else:
            self.log.error(f"An error occurred: {response_data.get('message', 'Unknown error')}")

    def process_changes(self, event=None):
        """
        Process changes
        """
        self.log.debug(f'[[{self.rule_name}]]: was triggered by: [{event.name if event else "None"}] with event value [{event.value if event else "None"}]')

        if energy_price_sell_item.get_value(0.0) < 0.0:
            new_export_limit = 0
        else:
            new_export_limit = 15100

        current_grid_export_limit = grid_export_limit_item.get_value(0.0)

        if new_export_limit != current_grid_export_limit:
            grid_export_limit_item.oh_post_update(new_export_limit)
            self.log.info(f"Setting new grid export limit to: {new_export_limit} W. (Current limit is: {current_grid_export_limit})")

    def new_export_limit(self, event=None):
        self.log.debug(f'[[{self.rule_name}]]: was triggered by: [{event.name if event else "None"}] with event value [{event.value if event else "None"}]')
        self.log.info(f"Calling script to set new export limit")
        args_list = [
            'someusername@server_hostname',
            '~/fronius-export-limit-setter/.venv/bin/python',
            '~/fronius-export-limit-setter/main.py',
            '-e', str(grid_export_limit_item.value),
            '-f', 'http://fronius.home',
            '-p', 'SOMESECRETPASSWORD'
        ]
        self.execute_subprocess(self._on_subprocess_finished, 'ssh', *args_list, capture_output=True)

DynamicPowerReduction()
```

## Liability and Warranty

This software is provided "as is" without any warranty or support. Use it at your own risk. The author shall not be held liable for any damages, whether direct or indirect, resulting from the use of this software.

## Project Origin and License

This script is derived from the original work by shadow7412 on GitHub:
[Original Script](https://github.com/shadow7412/fronius-driver/blob/master/main.py)

The original script was designed for Home Assistant integration and released under the GPL-3.0 license. This modified version generalizes the functionality to be used independently of any specific home automation system.

**License**: GPL-3.0

This updated script can be found at: [Fronius Export Limit Setter](https://github.com/besynnerlig/Fronius-Export-Limit-Setter)
