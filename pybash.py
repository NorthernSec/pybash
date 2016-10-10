# Imports
import colorama
import contextlib
import getpass
import io
import os
import pickle
import re
import socket
import subprocess
import sys
import traceback

# Overrides
if sys.version_info >= (3, 0):
  raw_input = input

# Constants
REG_OTHER        = re.compile(",((?! ,).)* ,")
REG_BASHVARS     = re.compile("^((?!\\\\).)?(\$\w+)|(\${\w+})")
REG_PY_MULTILINE = re.compile("""^(def|if|\"\"\"((?!\"\"\").)*|\'\'\'((?!\'\'\').)*)""")

WIN = True if os.name == 'nt' else False

defaultSettings={
  "colors": {
    "user": colorama.Fore.RED,
    "host": colorama.Fore.YELLOW,
    "path": colorama.Fore.CYAN,
    "text": colorama.Fore.RESET},
  "globs": {},
  "vars": {},
  "bash": True,
  "bash_binary": "/bin/bash",
  "home": os.path.expanduser("~"),
  "history": []
}


@contextlib.contextmanager
def stdoutIO(stdout=None):
  old = sys.stdout
  if stdout is None:
    stdout = io.StringIO()
  sys.stdout = stdout
  yield stdout
  sys.stdout = old


class pybash():
  def __init__(self, bash=True, bash_binary="/bin/bash"):
    self.settings = defaultSettings
    self.settings["bash"] = bash
    self.settings["bash_binary"] = bash_binary
    self.settings["globs"]["_term"] = self
    colorama.init()


  def history(self, line=None, limit=50):
    if line:
      return "Not implemented yet"
    _h = []
    for i, line in enumerate(self.settings["history"][-limit:]):
      _h.append(" "+str(i)+" "*(5-len(str(i))) + " " + line)
    return _h


  def _saveSession(self, path=None):
    if not path: path = os.path.join(self.settings["home"], ".pybash/session.pkl")
    if not os.path.exists(os.path.dirname(path)): os.makedirs(os.path.dirname(path))
    try:
      pickle.dump(self.settings, open(path, "wb"))
      print("Session saved! [%s]"%path)
    except Exception as e:
      print("Could not save session! (%s)"%e)


  def _loadSession(self, path=None):
    if not path: path = os.path.join(self.settings["home"], ".pybash/session.pkl")
    try:
      self.settings=pickle.load(open(path, "rb"))
      print("Session loaded! [%s]"%path)
    except:
      print("Could not load session: %s"%path)


  def _getCurs(self):
    def color(data, setting):
      return self.settings["colors"][setting] + data + \
             self.settings["colors"]["text"]

    if not self.settings["bash"]:
      return ">>> "
    else:
      user = getpass.getuser()
      host = socket.gethostname()
      path = os.getcwd()
      if path.startswith(self.settings["home"]):
        path = path.replace(self.settings["home"], "~", 1)
      return "%s@%s:%s$ "%(color(user, "user"), color(host, "host"), 
                           color(path, "path"))


  def execPython(self, command):
    with stdoutIO() as s:
      try:
        exec(command, self.settings["globs"], self.settings["vars"])
      except:
        traceback.print_exc()
    return s.getvalue()[:-1]


  def execBash(self, command):
    environment = {x: str(y) for x, y in self.settings["vars"].items()}
    _c, payload = command.split(" ", 1)+[""]*(2-len(command.split(" ", 1)))
    if   _c == "cd":              os.chdir(payload)
    elif _c in ["clear", "cls"]:  os.system("cls" if WIN else "clear")
    elif _c == "history":
      if payload:  print("not implemented yet")
      else:        print("\n".join(self.history()))
    elif _c in ["nano", "vi"]:
      print("You shouldn't run %s from pybash"%command.split()[0])
    else:
      return subprocess.Popen(command, shell=True, env=environment, 
                              executable=self.settings["bash_binary"],
                              stdout=subprocess.PIPE).stdout.read().decode('utf-8')[:-1]


  def _pybashCommand(self, command):
    _c, payload = command.split(" ", 1)+[""]*(2-len(command.split(" ", 1)))
    if   _c in [":py", ":python"]: self.settings["bash"] = False
    elif _c in [":bash", ":sh"]:   self.settings["bash"] = True
    elif _c in [":load"]:          self._loadSession(payload)
    elif _c in [":save"]:          self._saveSession(payload)
    elif _c in [":exit"]:          sys.exit()
    else:                          return False
    return True


  def _parseCommand(self, command):
    if self._pybashCommand(command): return
    for _command in set([x.group() for x in REG_OTHER.finditer(command)]):
      if self.settings["bash"]: value = self.execPython(_command[1:-2])
      else:                     value = self.execBash(_command[1:-2])
      command = command.replace(_command, repr(value))
      if not command: return
    if self.settings["bash"]: return self.execBash(command)
    else:                     return self.execPython(command)


  def _interactiveShell(self):
    multiline = None
    while True:
      try:
        data = raw_input("... " if multiline else self._getCurs())
        if not data and not multiline:
          continue
        self.settings["history"].append(data)
        if REG_PY_MULTILINE.match(data):
          multiline = data
          continue
        if multiline:
          if data:
            multiline += "\n%s"%data
            continue
          else:
            data = multiline
            multiline = None
        data = self._parseCommand(data)
        if data: print(data)
      except KeyboardInterrupt:
        print()
      except EOFError:
        print()
        break
      except SystemExit:
        sys.exit()
      except:
        traceback.print_exc()
        sys.exit()


  def runScript(self, _file):
    try:
      script = open(_file).read().splitlines()
      multiline = None
      for line in script:
        if not line and not multiline:
          continue
        if REG_PY_MULTILINE.match(line):
          multiline = line
          continue
        if multiline:
          if line:
            multiline += "\n%s"%line
            continue
          else:
            line = multiline
            multiline = None
        data = self._parseCommand(line)
        if data: print(data)
    except FileNotFoundError:
      print("No such file or directory: %s"%script)


if __name__ == '__main__':
  import argparse
  description='''Interpreter for both python and bash'''
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('file', metavar='file', nargs='?', help='Script to run')
  parser.add_argument('-p',   action='store_true',       help='Start script with python instead of bash')
  
  args = parser.parse_args()

  _term = pybash(bash=(not args.p))
  if args.file: _term.runScript(args.file)
  else:
    _term._interactiveShell()
