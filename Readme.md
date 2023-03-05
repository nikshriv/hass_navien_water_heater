Navien Water Heater Custom Integration
============
Control and monitor the state of Navien water heaters that are connected by a NaviLink hub. The integration has been completely rewritten to adjust to the recent changes to the backend. To install this integration, you can use HACS to perform the installation or you can do it manually. If you want to use HACS, you will first need to install the HACS integration which can be found at https://hacs.xyz/. 

To install the integration with HACS:
1. Navigate to HACS and add a custom repository  
    **URL:** https://github.com/nikshriv/hass_navien_water_heater
    **Category:** Integration
2. Install module as usual
3. Restart Home Assistant

For manual installation:
1. Install the File Editor add-on from the HA Addon Store.
2. Use the File Editor to create a directory called custom_components in your /config directory
3. Create another directory called navien_water_heater in the custom_components directory.
4. Clone my repository
5. Then upload the entire content of the navient_water_heater directory from the repository into the navien_water_heater directory you created
6. Restart HA
7. Go to Device and Services under Settings in HA and add the Navien integration.

https://www.buymeacoffee.com/nikshriv
