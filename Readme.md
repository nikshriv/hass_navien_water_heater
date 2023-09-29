# Navien Water Heater Custom Integration
Control and monitor the state of Navien water heaters which are connected to the Navien cloud portal via a [NaviLink or NaviLink Lite](https://www.navieninc.com/accessories/navilink) control system.

## Installation
To install this integration, you can use HACS to perform the installation or you can do it manually. If you want to use HACS, you will first need to install the HACS integration which can be found at https://hacs.xyz/. 

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
4. Clone this repository
5. Upload the entire content of the navien_water_heater directory from the repository into the navien_water_heater directory you created
6. Restart Home Assistant
7. Go to Device and Services under Settings in Home Assistant and add the Navien integration.

## Preheat/Recirculation "Hot Button" functionality
For water heaters with hot water recirculation functionality (e.g. A or A2) via dedicated External Loop or [NaviCirc](https://www.navieninc.com/accessories/navicirc), you will also be able to directly control [Hot Button](https://www.navieninc.com/accessories/hotbutton) functionality if a Hot Button PCB is also installed. This PCB is pre-installed on A2 models, but must be [installed](https://www.navieninc.com/downloads/hotbutton-installation-instructions-en) as an [add-on kit](https://www.navieninc.com/products/npe-240a/accessories) for the older A models. Before purchasing this add-on kit, check your main PCB's model version (P20 or newer) IAW Step 2.2.4. The physical buttons _do not_ need to be connected to gain hot button functionality through this integration. _Check the NaviLink app to ensure everything is configured properly (Hot Button instead of Schedule options)_. If you install this integration without Hot Button functionality and later enable it, just Reload the integration to add the Recirculation switch entity. **You will have a recirculation switch entity that can be manually controlled via dashboard, voice commands, and/or automation!**

The preheat/recirculation settings (i.e. parameters) are inconsistently named between the A and A2 models. They can also be misleading (e.g. interval time is duration, but sample time is the interval time). This table should help you decode these settings to more effectively configure and troubleshoot your water heater. Since the Hot Button function is not standard on A models, better descriptions of these parameters can be found under Step 7.5.1.2 on pg 99 and Category 4 of Step 7.5.1.3 on pg 102 of the [A2 installation manual](https://www.navieninc.com/downloads/npe-2-installation-and-operation-manual-en):

|    A (See Note 1)     |    A2   | Description | Notes |
| -------- | ------- | ------- |------- |
| Preheat Pump Output Time (P.12) | Recirc Interval Time | Recirculation Duration | See Note 2. Hot Button 5 mins |
| Preheat Interval Time (P.14) | Recirc Sample Time | Recirculation Interval | Hot Button N/A (not mentioned in manuals) |
| Preheat Off Offset Temp (P.15) | Recirc off Diff. Temp | Recirculation Off Delta | See Note 2. Hot Button --- |
| On-demand Pipe Target Length (P.16) | Fixture Distance | Recirculation Off without External Temp Sensor | See Note 3 |

1. For the A model, set IAW Step 6.5 on pgs 65-68 of the [A installation manual](https://www.navieninc.com/downloads/npe-a-s-manuals-installation-manual-en).
2. There are DIP switches on the Hot Button PCB (see pg 34 of the A2 installation manual). [Some users](https://community.home-assistant.io/t/navien-hot-water-heater-navilink/330044/47) find they must set DIP switch 2 to ON for the recirculation function to heat to the setpoint. This setting changes the behavior of both of these settings as described on pg 102 of the [A2 installation manual](https://www.navieninc.com/downloads/npe-2-installation-and-operation-manual-en).
3. If recirculation does not stay on long enough after Hot Button activation, try increasing to a much higher pipe length.

## Sample card
Here is an example of a card that can be used to monitor and control a water heater including recirculation. It uses the following custom cards:
- [ApexCharts](https://github.com/RomRider/apexcharts-card)
- [Mushroom](https://github.com/piitaya/lovelace-mushroom)
- [Card Mod](https://github.com/thomasloven/lovelace-card-mod)
- [Stack In Card](https://github.com/custom-cards/stack-in-card)

![image](https://github.com/GitHubGoody/hass_navien_water_heater/assets/46235745/42b851b3-7a48-4b8e-89b0-b4285a8396bb)

https://www.buymeacoffee.com/nikshriv
