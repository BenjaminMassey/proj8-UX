# Project 8: User interface for uthenticated brevet time calculator service

Made by Ben Massey for CIS 322 March 2018

Mostly just project 7 - check my github

## Additions

Changed system of logins at least partially - using WTForms stuff. This means
a separate login page, a way to logout, CRSF security, and a remember me.
Registering users still works the same way.

## How to use

1. Create a MongoDB database (I used m-lab)

2. Create a collection titled "users" in that database

3. Create a collection titled "times" in that database

4. Create your credentials.ini file based on credentials-skel.ini

5. Run the program

- Basic Python 
	- python flask-brevets.py
- Basic Docker
	- docker build -t NAME .
- Docker-Compose
	- docker-compose up
	
6. Go to the webpage (defined by your machine ip and your config port) and have fun!