This repository is relatively straightforward in that it takes traffic from an SSC-Tracker server, converts the .json output to FSD for Euroscope to import as traffic. All normal Euroscope features work with this and traffic work as if you are on the live VATSIM network.

Requirements:

* Euroscope (Windows / Wine; https://www.euroscope.hu/wp/)
* Python (v3.8 +)
* SSC-Tracker (https://ssc-tracker.org)



Features:

1. Checks FSHub.io for airline traffic and pulls flight plans
2. Takes and injects all SSC traffic into Euroscope
3. Checks all SSC traffic for a VATSIM flight plan
4. Auto-assigns SSR
5. Auto-assumes all traffic detected for easy identification



Euroscope Configuration:

* If you do use VATSIM, you may configure Euroscope as usual, but you must not connect to the network.

Configuration Steps

1. Anything (anything at all!) can go into the name, VATSIM ID and password fields (even if you don't have a VATSIM account)
2. Select whatever callsign you would like to use
3. Set your rating and position - again, this does not need to match your VATSIM role (if you have any, including Delivery, FIS, Tower etc.)
4. Change the server from AUTOMATIC to 127.0.0.1 / localhost / your machine's IP
5. Uncheck 'Connect to VATSIM' below
6. Before pressing 'Connect' in the bottom left, open SSC-Tracker and run SSC - Euroscope.py



