# Microday

Microday is a command line todo-list that lays out a schedule for your day
based on how much time you expect to spend on each todo-item.


[![asciicast](https://asciinema.org/a/QGTNJSu7p3BzpSTTPi43HATR9.png)](https://asciinema.org/a/QGTNJSu7p3BzpSTTPi43HATR9)

Todo-lists are stored in (and loaded from) a human-readable markdown format:

    # Todos

    - Task1
    - Task2

Start the script and it will ask you how much time you want to spend on each item.

    $ How many minutes do you need for Task1? (enter=later) 10

This creates a second list called 'Tasks' in your markdown file, which lays out
how much time you need for all your todos and when you will be done with the last
one. Starting times are always ending in 0 or 5, so you may have some rest time
in between tasks, which is just fine.

    # Tasks

    12:30 - 0:10h Task1
    12:40 - 0:05h Task2
    12:45 Feierabend

Feierabend is German for the end of a work day.

## Setup

Requires Python 3 and pip.

    $ pip install microday

## Usage

Start microday from a shell with `python -m microday`. It will then create a 
markdown file with your todos in the current working directory.

    usage: microday.py [-h] [filename]

    Meticulously plan your day minute-by-minute

    positional arguments:
    filename    Filename of your todo doc, default is 'todo_<y-m-d>.md'

    optional arguments:
    -h, --help  show this help message and exit
