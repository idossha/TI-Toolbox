

1. decide what images to use based  on the eeg_electrodes.csv files created by SimNIBS
- can possibly use same 10-10 image for multiple nets.

2. make sure multipolar logic allow the user to select more than 4 pairs. this will allow us future compatibility when mTI might have more electrodes. 

3. each channel should have a unique color.

4. each configuration should have unique names. 


example:

uniploar TI:

Channel 1: red
Channel 2: green

multipolar TI:

TI_A Channel 1: red
TI_A Channel 2: green

TI_B Channel 1: blue
TI_B Channel 2: yellow
