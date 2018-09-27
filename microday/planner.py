import pdb
import re
import sys
import select
import subprocess
from datetime import datetime, timedelta
from time import sleep
from termcolor import cprint, colored

COLOR_LOG = 'grey'
COLOR_ACCENT = 'green'


def user_choice(text):
    choice = None
    while choice not in ['y', 'n', '']:
        choice = input(colored('{} [Y/n] '.format(text), COLOR_ACCENT))
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
        self.instructions = "[enter] für nächsten Task\n[t] für neuen task\n[s] für diesen skippen"
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
                if line == '\n' or line.strip() == '# Todos':
                    continue

                if line.startswith('# Zeitplan'):
                    planning = True

                if planning:
                    self.process_task(line)
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

        if self.tasks[self.cur]['start'] - datetime.now() < timedelta(minutes=5):
            cprint('Nimm dir eine kurze Pause und beginne dann mit {}'.format(
                self.tasks[self.cur]['task']
            ), COLOR_LOG)
            return

        if self.tasks[self.cur]['start'] > datetime.now():
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

        self.to_disk()

        if self.tasks[self.cur]['start'] <= datetime.now():
            cprint('Nächste Aufgabe..', COLOR_LOG)
            self.cur += 1

    def insert_new_task(self):
        text = input(colored('Aufgabe eingeben: ', COLOR_ACCENT))
        duration = int(input(colored('Wieviele Minuten?: ', COLOR_ACCENT)))

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

    def task_to_todo(self, index):
        self.todos.insert(0, self.tasks[index]['task'])
        del self.tasks[index]
        self.to_disk()

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
            sys.stdout.write(colored(announcement, COLOR_ACCENT))
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
            sys.stdout.write(colored(update_tmpl.format(
                running_clock,
                cur_task['task'],
                text
            ), COLOR_ACCENT))
            self.announce(self.cur + 1, left)

    def run(self):
        cprint('--- Microday 1.0 ---\n', 'blue')
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
                    self.insert_new_task()
                elif choice == 's':
                    self.task_to_todo(self.cur)

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
        def maybe_colored(text, color):
            return colored(text, color) if colors else text

        out = ""
        if len(self.todos) > 0:
            out += maybe_colored("# Todos", 'blue')
            out += "\n\n- "
            out += '\n- '.join(self.todos)
            out += "\n"

        if len(self.tasks) > 0:
            out += "\n"
            out += maybe_colored("# Zeitplan", 'blue')
            out += "\n\n"
            out += "\n".join([maybe_colored("{} - {}h {}".format(
                task['start'].strftime("%H:%M"),
                strfdelta(task['duration'], "{h}:{m:02d}"),
                task['task']
            ), 'red' if i == self.cur else 'white') for i, task in enumerate(self.tasks)])
            end = self.tasks[-1]['start'] + self.tasks[-1]['duration']
            out += "\n{} - Feierabend\n".format(end.strftime("%H:%M"))

        return out

    def to_disk(self):
        with open(self.datafn, 'w') as f:
            f.write(self.serialize(colors=False))


if __name__ == '__main__':
    planner = Microday('todo.md')
    try:
        planner.run()
    except KeyboardInterrupt:
        planner.to_disk()
        cprint('\nZeitplan gespeichert. Bye!\n', COLOR_ACCENT)
        raise SystemExit
