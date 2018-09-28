#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import os
import re
import select
import subprocess
import sys
from datetime import datetime, timedelta
from time import sleep

import colored
from colored import stylize

from .__version__ import __version__ as VERSION

COLOR_LOG = colored.fg('dark_gray')
COLOR_ACCENT = colored.fg('green')
COLOR_INFO = colored.fg('blue')
COLOR_CURRENT_TASK = colored.fg('red')
COLOR_DEFAULT = colored.fg('white')

def cprint(txt, color):
    print(stylize(txt, color))

def user_choice(text):
    choice = None
    while choice not in ['y', 'n', '']:
        choice = input(stylize('{} [Y/n] '.format(text), COLOR_ACCENT))
    print("")
    return choice in ['y', '']

def strfdelta(tdelta, fmt='{m}:{s:02d}'):
    d = {"d": tdelta.days}
    d["h"], rem = divmod(tdelta.seconds, 3600)
    d["m"], d["s"] = divmod(rem, 60)
    return fmt.format(**d)


class Microday(object):
    todos = []  # todos are unsorted
    tasks = []  # tasks are scheduled

    def __init__(self, datafn):
        cprint('--- microday {} ---\n'.format(VERSION), COLOR_INFO)
        self.instructions = "[enter] Vorwärts \n[t] Task einfügen \n[s] Diesen überspringen"
        self.datafn = datafn
        try:
            self.from_disk(datafn)
        except FileNotFoundError:
            cprint("{} nicht gefunden. Probiere 'todo.md'..".format(datafn), COLOR_LOG)
            try:
                self.from_disk('todo.md')
            except FileNotFoundError:
                cprint('{} auch nicht gefunden'.format('todo.md'), COLOR_LOG)
                self.from_input()
                self.to_disk()

    def announce(self, index, left):
        if left is None or left.seconds not in [0, 60]:
            return

        task = self.tasks[index]['task']
        cmd = "say -v Anna {}: {}"

        if left.seconds == 60:
            subprocess.run(cmd.format('In einer Minute beginnt', task),
                           shell=True)

        if left.seconds == 0:
            subprocess.run(cmd.format('Jetzt beginnt', task),
                           shell=True)

    def from_disk(self, datafn):
        with open(datafn) as f:
            planning = False
            for line in f.readlines():
                if line == '\n' or line.strip() == '# Todos':
                    continue

                if line.startswith('# Zeitplan'):
                    planning = True

                if planning:
                    self.process_task(line)
                else:
                    self.process_todo(line.strip())

    def from_input(self):
        txt = "Guten Morgen! Die <{}> ist noch leer.\nWas möchtest du heute tun? [leer=weiter]\n"
        cprint(txt.format(self.datafn), COLOR_ACCENT)

        while(True):
            ans = input(stylize('Aufgabe eingeben: ', COLOR_LOG))
            if ans != '':
                self.process_todo(ans)
            else:
                break
        

    def create_task(self, start, duration, task):
        offset = start.minute % 5
        if offset not in [0, 5]:
            start = start + timedelta(minutes=(5 - offset))

        return {
            'start': start,
            'duration': duration,
            'task': task
        }

    def plan_todos(self):
        new_todos = []
        for task in self.todos:
            q_tmpl = "Wie viele Minuten brauchst du für {}? (enter=later) "
            time = input(q_tmpl.format(task))
            if time == '':
                new_todos.append(task)
            else:
                duration = timedelta(minutes=int(time))
                if len(self.tasks) == 0:
                    start = datetime.now()
                else:
                    start = self.tasks[-1]['start'] + \
                        self.tasks[-1]['duration']
                    if start < datetime.now():
                        start = datetime.now()

                task = self.create_task(start, duration, task)
                self.tasks.append(task)
        self.todos = new_todos
        self.to_disk()

    def process_task(self, text):
        exp = r"(\d{1,2})[.:]+(\d{2}).+(\d{1,2})[:.](\d{2})[hm]?[\s]?([^\n]+)"
        m = re.match(exp, text)

        if m:
            h, m, dur_h, dur_m, task = m.groups()
            self.tasks.append({
                'start': datetime.now().replace(hour=int(h), minute=int(m)),
                'duration': timedelta(hours=int(dur_h), minutes=int(dur_m)),
                'task': task
            })

    def process_todo(self, text):
        m = re.match(r'(?:-\s)?(.+)', text)
        if m:
            self.todos.append(m.group(1))

    def reschedule(self):
        cprint('Neuplanung..', COLOR_LOG)

        if self.tasks[self.cur]['start'] > datetime.now():
            if self.tasks[self.cur]['start'] - datetime.now() < timedelta(minutes=5):
                cprint('Nimm dir eine kurze Pause und beginne dann mit {}'.format(
                    self.tasks[self.cur]['task']
                ), COLOR_LOG)
                return
            else:
                cprint('Aktuelle Aufgabe wird vorgezogen..', COLOR_LOG)
                self.tasks[self.cur]['start'] = datetime.now()
                start = self.cur
        else:
            text = self.tasks[self.cur]['task']
            dur = datetime.now() - self.tasks[self.cur]['start']
            self.tasks[self.cur]['duration'] = dur
            start = self.cur + 1
            cprint('Tatsächliche Zeit für {} waren {}..'.format(
                text, strfdelta(dur)), COLOR_LOG)

        for i in range(start, len(self.tasks)):
            if i > 0:
                prev = self.tasks[i - 1]
                start = prev['start'] + prev['duration']
            else:
                start = datetime.now()
            duration = self.tasks[i]['duration']
            text = self.tasks[i]['task']
            self.tasks[i] = self.create_task(start, duration, text)

        if self.tasks[self.cur]['start'] <= datetime.now():
            cprint('Nächste Aufgabe..', COLOR_LOG)
            self.cur += 1

    def insert_new(self):
        text = input(stylize('Aufgabe eingeben: ', COLOR_ACCENT))
        duration = input(stylize('Wieviele Minuten? [leer=todo-liste]: ', COLOR_ACCENT))

        if len(duration) > 0:
            duration = int(duration)
            next_task = self.cur + 1
            start = self.tasks[next_task]['start'] \
                if len(self.tasks) > (next_task)   \
                else self.tasks[self.cur]['start'] \
            + self.tasks[self.cur]['duration']

            self.tasks.insert(
                next_task,
                self.create_task(
                    start,
                    timedelta(minutes=duration),
                    text
                )
            )
        else:
            self.todos.append(text)

    def task_to_todo(self, index):
        self.todos.insert(0, self.tasks[index]['task'])
        del self.tasks[index]

    def print_announcement_line(self):
        # Reset command prompt with
        sys.stdout.write("\r{}".format(" " * 80))

        cur_task = self.tasks[self.cur]
        next_task = self.tasks[self.cur +
                               1] if len(self.tasks) > self.cur + 1 else None

        # Case: Current task hasn't started yet
        if cur_task['start'] > datetime.now():
            left = cur_task['start'] - datetime.now()
            announcement = "\r{taskname} beginnt in {timeleft}".format(
                taskname=cur_task['task'],
                timeleft=strfdelta(left, '{m}:{s:02d}'))
            if left > timedelta(minutes=5):
                announcement += " [enter=starte jetzt]"
            sys.stdout.write(stylize(announcement, COLOR_ACCENT))
            self.announce(self.cur, left)

        # Case: Current task has started in the past
        else:
            if (self.cur + 1) < len(self.tasks):
                text = next_task['task']
                left = next_task['start'] - datetime.now()
            else:
                text = "Fertig!"
                left = None

            running_clock = strfdelta(
                datetime.now() - cur_task['start'],
                '{m}:{s:02d}'
            )

            update_tmpl = "\r{} vergangen bei: {}, als nächstes: {}. "
            sys.stdout.write(stylize(update_tmpl.format(
                running_clock,
                cur_task['task'],
                text
            ), COLOR_ACCENT))
            self.announce(self.cur + 1, left)

    def run(self):
        # Constructor loads state from disk
        remaining = self.select_starting_point()

        if len(self.todos) > 0:
            print(self.serialize())
            if user_choice('Zeitplanung für offene Todos starten?'):
                self.plan_todos()

        print(self.serialize())
        remaining = self.select_starting_point()

        if len(remaining) == 0:
            cprint("Alle Aufgaben liegen in der Vergangenheit", COLOR_ACCENT)
            return

        print(self.instructions + '\n')

        while(True):
            is_user_input_available = select.select(
                [sys.stdin, ], [], [], 0.0)[0]

            if is_user_input_available:
                choice = sys.stdin.readline().strip()
                if choice == '':
                    self.reschedule()
                elif choice == 't':
                    self.insert_new()
                elif choice == 's':
                    self.task_to_todo(self.cur)
                
                self.to_disk()

                print(self.serialize())

                if self.cur == len(self.tasks):
                    cprint("Fertig!", COLOR_ACCENT)
                    break

                print(self.instructions + "\n")

            self.print_announcement_line()
            sleep(1)

    def select_starting_point(self):
        remaining = [i for i, t in enumerate(self.tasks)
                     if t['start'] + t['duration'] >= datetime.now()]
        self.cur = remaining[0] if len(remaining) > 0 else 0
        return remaining

    def serialize(self, colors=True):
        def maybe_stylize(text, color):
            return stylize(text, color) if colors else text

        out = ""
        if len(self.todos) > 0:
            out += maybe_stylize("# Todos", COLOR_INFO)
            out += "\n\n- "
            out += '\n- '.join(self.todos)
            out += "\n"

        if len(self.tasks) > 0:
            out += "\n"
            out += maybe_stylize("# Zeitplan", COLOR_INFO)
            out += "\n\n"
            out += "\n".join([maybe_stylize("{} - {}h {}".format(
                task['start'].strftime("%H:%M"),
                strfdelta(task['duration'], "{h}:{m:02d}"),
                task['task']
            ), COLOR_CURRENT_TASK if i == self.cur else COLOR_DEFAULT) for i, task in enumerate(self.tasks)])
            end = self.tasks[-1]['start'] + self.tasks[-1]['duration']
            out += "\n{} - Feierabend\n".format(end.strftime("%H:%M"))

        return out

    def to_disk(self):
        with open(self.datafn, 'w') as f:
            f.write(self.serialize(colors=False))
        fullp = os.path.join(os.path.dirname(os.path.realpath(self.datafn)), self.datafn)
        cprint('{} gespeichert.'.format(fullp), COLOR_LOG)



def main():
    if sys.version_info < (3, 6):
        print("Sorry, microday requires at least Python 3.6")
        sys.exit()
        
    default_filename = 'todo_{}.md'.format(datetime.now().strftime("%y-%m-%d"))
    parser = argparse.ArgumentParser(
        description='Meticulously plan your day minute-by-minute')
    parser.add_argument('filename', 
        nargs='?',
        type=str, 
        default=default_filename,
        help="Filename of your todo doc, default is 'todo_<y-m-d>.md'>"
    )
    args = parser.parse_args()

    try:
        md = Microday(args.filename)
    except KeyboardInterrupt:
        cprint('\n\nNagut, dann halt nicht.', COLOR_ACCENT)
        sys.exit()

    try:
        md.run()
    except KeyboardInterrupt:
        remaining = md.select_starting_point()
        if len(remaining) > 0:
            put_back = user_choice(
                '\n\n{} offene Tasks zurück zu den Todos legen?'.format(
                    len(remaining)))
            if put_back:
                [md.task_to_todo(i) for i in remaining[::-1]]
        else:
            print()

        md.to_disk()
        cprint('Bye!\n', COLOR_ACCENT)
        raise SystemExit

if __name__ == '__main__':
    main()
