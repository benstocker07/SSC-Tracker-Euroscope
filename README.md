This repository is relatively straightforward in that it takes traffic from an SSC-Tracker server, converts the .json output to FSD for Euroscope to import as traffic. All normal Euroscope features work with this and traffic work as if you are on the live VATSIM network.

Requirements:

* Euroscope (Windows / Wine; https://www.euroscope.hu/wp/)
* Python (v3.8 +)
* SSC-Tracker (https://ssc-tracker.org)

Euroscope Configuration:

* You may configure Euroscope however you would normally, but you must not connect to the network as normal.

Configuration Steps

1. Keep your name, VATSIM ID and password the same
2. Select whatever callsign you would like to use
3. Set your rating and position (Delivery, FIS, Tower etc.)
4. Change the server from AUTOMATIC to 127.0.0.1 / localhost / your machine's IP
5. Uncheck 'Connect to VATSIM' below
6. Before pressing 'Connect' in the bottom left, open SSC-Tracker and run SSC - Euroscope.py



