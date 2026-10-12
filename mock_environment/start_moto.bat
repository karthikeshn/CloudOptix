@echo off
echo Starting Persistent Moto Server on port 5000...
echo All mock resources will persist to disk in mock_environment/state
moto_server -p 5000 --persist
