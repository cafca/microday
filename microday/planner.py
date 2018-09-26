import pdb
import re
import sys
import select
import subprocess
from datetime import datetime, timedelta
from time import sleep
from termcolor import cprint, colored


def user_choice(text):
    choice = None
    while choice not in ['y', 'n', '']:
        choice = input('{} [Y/n] '.format(text))
    return choice in ['y', '']


def strfdelta(tdelta, fmt):
    d = {"d": tdelta.days}
    d["h"], rem = divmod(tdelta.seconds, 3600)
    d["m"], d["s"] = divmod(rem, 60)
    return fmt.format(**d)


class Microday(object):
    def __init__(self, datafn):
        self.instructions = "\n[enter] für nächsten Task\n[t] für neuen task\n[s] für diesen skippen\n"
        self.regex = None
        self.tasks = []
        self.todos = []
        self.datafn = datafn
        self.from_disk(datafn)

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
                if line == '\n' or line.strip() in [colored('# Todos', 'blue'), '# Todos']:
                    continue

                if line.startswith(colored('# Zeitplan', 'blue')) or line.startswith('# Zeitplan'):
                    planning = True

                if planning:
                    self.process_entry(line)
                else:
                    self.process_todo(line.strip())

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

    def process_entry(self, text):
        exp = r"(\d{1,2})[.:]+(\d{2}).+(\d{1,2})[:.](\d{2})[hm]?[\s]?([^\n]+)"
        m = re.match(exp, text)

        if m:
            h, m, dur_h, dur_m, task = m.groups()
            self.tasks.append({
                'start': datetime.now() \
                    .replace(hour=int(h), minute=int(m)),
                'duration': timedelta(hours=int(dur_h), minutes=int(dur_m)),
                'task': task
            })

    def process_todo(self, text):
        m = re.match(r'(?:-\s)?(.+)', text)
        if m:
            self.todos.append(m.group(1))

    def reschedule(self, current):
        if self.tasks[current]['start'] > datetime.now():
            self.tasks[current]['start'] = datetime.now()
            start = current
        else:
            dur = datetime.now() - self.tasks[current]['start']
            self.tasks[current]['duration'] = dur
            start = current + 1

        for i in range(start, len(self.tasks)):
            prev = self.tasks[i - 1]
            self.tasks[i] = self.create_task(
                prev['start'] + prev['duration'],  # new start time
                self.tasks[i]['duration'],
                self.tasks[i]['task']
            )
        print("\n" + self.serialize() + "\n")
        self.to_disk()

    def run(self):
        if len(self.todos) > 0:
            print(self.serialize())
            if user_choice(colored('Zeitplanung für offene Todos starten?', 'green')):
                self.plan_todos()
                print("\n")

        print(self.serialize())
        print("\n")
        remaining = [i for i, t in enumerate(self.tasks)
                     if t['start'] + t['duration'] >= datetime.now()]

        if len(remaining) == 0:
            cprint("Alle Aufgaben liegen in der Vergangenheit", 'green')
            return

        cur = remaining[0]
        while(True):
            # If user entered something since last loop
            if (select.select([sys.stdin, ], [], [], 0.0)[0]):
                choice = sys.stdin.readline().strip()
                if choice == '':
                    cprint('Neuplanung..', 'grey')
                    self.reschedule(cur)
                    if self.tasks[cur]['start'] <= datetime.now():
                        cprint('Nächste Aufgabe..', 'grey')
                        cur += 1
                        if cur >= len(self.tasks):
                            cprint("Fertig!", 'green')
                            break
                elif choice == 't':
                    task = input(colored('Aufgabe eingeben: ', 'green'))
                    duration = int(input(colored('Wieviele Minuten?: ', 'green')))
                    start = self.tasks[cur + 1]['start'] if len(self.tasks) > (cur + 1) else self.tasks[cur]['start'] + self.tasks[cur]['duration']
                    self.tasks.insert(
                        cur + 1, self.create_task(start, timedelta(minutes=duration), task))
                    print(self.serialize())
                elif choice == 's':
                    self.todos.insert(0, self.tasks[cur]['task'])
                    del self.tasks[cur]
                    self.to_disk()
                    print(self.serialize())
                    if cur == len(self.tasks):
                        cprint("Fertig!", 'green')
                        break

                print(self.instructions)

            sys.stdout.write("\r{}".format(" " * 80))

            if self.tasks[cur]['start'] > datetime.now():
                left = self.tasks[cur]['start'] - datetime.now()
                sys.stdout.write(colored("\r{} beginnt in {} [enter=starte jetzt]".format(
                    self.tasks[cur]['task'],
                    strfdelta(left, '{m}:{s:02d}')
                ), 'green'))
                self.announce(cur, left)
            else:
                if (cur + 1) < len(self.tasks):
                    next_task = self.tasks[cur + 1]['task']
                    left = self.tasks[cur + 1]['start'] - datetime.now()
                else:
                    next_task = "Fertig!"
                    left = None
                over = strfdelta(
                    datetime.now() - self.tasks[cur]['start'],
                    '{m}:{s:02d}'
                )

                update_tmpl = "\r{} vergangen bei: {}, als nächstes: {}. "
                sys.stdout.write(colored(update_tmpl.format(
                    over,
                    self.tasks[cur]['task'],
                    next_task
                ), 'green'))
                self.announce(cur + 1, left)

            sleep(1)

    def serialize(self):
        out = ""
        if len(self.todos) > 0:
            out += colored("# Todos", 'blue')
            out += "\n\n- "
            out += '\n- '.join(self.todos)
            out += "\n\n"

        if len(self.tasks) > 0:
            out += colored("# Zeitplan", 'blue')
            out += "\n\n"
            out += "\n".join(["{} - {}h {}".format(
                task['start'].strftime("%H:%M"),
                strfdelta(task['duration'], "{h}:{m:02d}"),
                task['task']
            ) for task in self.tasks])
            end = self.tasks[-1]['start'] + self.tasks[-1]['duration']
            out += "\n{} - Feierabend".format(end.strftime("%H:%M"))

        return out

    def to_disk(self):
        with open(self.datafn, 'w') as f:
            f.write(self.serialize())


if __name__ == '__main__':
    planner = Microday('todo.md')
    try:
        planner.run()
    except KeyboardInterrupt:
        planner.to_disk()
        cprint('\nZeitplan gespeichert. Bye!\n', 'green')
        raise SystemExit
