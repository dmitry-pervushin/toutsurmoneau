[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# ToutSurMonEau for Home Assistant

This component is based on existing one from @ooii

## Installation

### Option 1: HACS (simple, recommended)
Under HACS -> Integrations, select "+", search for ToutSurMonEau and install it.

### Option 2: Manual

On the HA machine:
```
cd YOUR_HASS_CONFIG_DIRECTORY    # same place as configuration.yaml
mkdir -p custom_components/
```
On the host machine:
```
git clone https://github.com/dmitry-pervushin/toutsurmoneau
```
copy toutsurmoneau/toutsurmoneau/custom_components/toutsurmoneau to YOUR_HASS_CONFIG_DIRECTORY/custom_components

## Configuration

Go to the Integrations menu in the Home Assistant Configuration UI and add ToutSurMonEau there. You would need
- counter id
- username (your email)
- password

## Contributing
Contributions are welcome! You are encouraged to submit PRs, bug reports, feature requests.

## Thanks

- The whole HomeAssistant team (https://homeassistant.io)
- Author of pysuez module (https://github.com/ooii/pySuez)
