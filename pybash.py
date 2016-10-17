# Color class
class color:
  GRAY     = '\033[90m';  END        = '\033[0m'
  RED      = '\033[91m';  BOLD       = '\033[1m'
  GREEN    = '\033[92m';  ITALIC     = '\033[3m'
  YELLOW   = '\033[93m';  UNDERLINE  = '\033[4m'
  BLUE     = '\033[94m';  INVERSE    = '\033[7m'
  PURPLE   = '\033[95m';  STRIKE     = '\033[9m'
  CYAN     = '\033[96m'
  WHITE    = '\033[97m'

# Imports
import contextlib
import getpass
import io
import os
import pickle
import re
import shutil
import socket
import string
import subprocess
import sys
import termios
import traceback
import tty
import types

# Temporarily import this from an external library
#  This will be implemented better, later on.
from AdvancedInput import AdvancedInput

# Constants
REG_OTHER        = re.compile(",((?! ,).)* ,")
REG_BASHVARS     = re.compile("^((?!\\\\).)?(\$\w+)|(\${\w+})")
REG_PY_MULTILINE = re.compile("""^(def |if |\"\"\"((?!\"\"\").)*|\'\'\'((?!\'\'\').)*)""")
NO_OUT = ['nano', 'vi', 'alsamixer', 'man']

WIN = True if os.name == 'nt' else False

defaultSettings={
  "colors": {
    "user": color.RED,
    "host": color.YELLOW,
    "path": color.CYAN,
    "text": color.END},
  "autoload": False,
  "autosave": False,
  "session": None,
  "globs": {},
  "vars": {},
  "bash": True,
  "bash_binary": "/bin/bash",
  "home": os.path.expanduser("~"),
  "history": []
}

HELP='''py or python               - Switch to python mode
bash or sh                 - Switch to bash mode
save [<session>]           - Save session
load [<session>]           - Load session
autosave <yes/no>          - Set session to autosave
autoload <yes/no>          - Set session to autoload
run <script>               - Run a script
clear                      - Clear the terminal
info or inspect <function> - Show source code of function
settings                   - Print the settings
help                       - Print this output
exit                       - Exit pybash'''


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
    self._input = AdvancedInput()
    self.settings["history"] = self._input.history
    self.line = None


  def history(self, line=None, limit=50):
    if line:
      try:
        if int(line) <= len(self.settings["history"]):
          self.line = self.settings["history"][int(line)]
      except:
          print("Please pass a line number")
    else:
      _h = []
      for i, line in enumerate(self.settings["history"][-limit:]):
        _h.append(" "+str(i)+" "*(5-len(str(i))) + " " + line)
      print("\n".join(_h))


  def _saveSession(self, path=None):
    if path and self.settings['session'] and path != self.settings['session']:
      print("The session path is different from the one loaded.")
      print("Would you like to continue on the new copy?")
      if AdvancedInput.confirm(True):
        self.settings['session'] = path
    if not path:
      if self.settings['session']: path = self.settings['session']
      else:                        path = os.path.join(self.settings["home"], ".pybash/session.pkl")
    if not os.path.exists(os.path.dirname(path)): os.makedirs(os.path.dirname(path))
    try:
      self.settings.pop('session')
      pickle.dump(self.settings, open(path, "wb"))
      self.settings['session'] = path
      print("Session saved [%s]"%path)
    except Exception as e:
      print("Could not save session! (%s)"%e)


  def _loadSession(self, path=None, auto=False):
    if not path: path = os.path.join(self.settings["home"], ".pybash/session.pkl")
    try:
      self.settings=pickle.load(open(path, "rb"))
      self._input.history = self.settings["history"]
      self.settings['session']=path
      print("Session loaded [%s]"%path)
    except:
      if not auto: print("Could not load session: %s"%path)


  def _clearSession(self):
    self.settings = defaultSettings


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
      if len(user+host+path)+3 > shutil.get_terminal_size().columns/2:
        path = "->/"+os.path.basename(os.path.normpath(path))
      return "%s@%s:%s$ "%(color(user, "user"), color(host, "host"),
                           color(path, "path"))


  def execPython(self, command):
    with stdoutIO() as s:
      try:
        exec(command, self.settings["globs"], self.settings["vars"])
        if command.startswith("def "):
          funct = command.split(" ")[1].split("(")[0]
          self.settings["vars"][funct].source = command
      except:
        traceback.print_exc()
    return s.getvalue()[:-1]


  def execBash(self, command):
    environment = {x: str(y) for x, y in self.settings["vars"].items()}
    _c, payload = command.split(" ", 1)+[""]*(2-len(command.split(" ", 1)))
    if   _c == "cd":              os.chdir(payload if payload else self.settings["home"])
    elif _c in ["clear", "cls"]:  os.system("cls" if WIN else "clear")
    elif _c == "history":         self.history(payload)
    elif _c in NO_OUT:
      try:
        subprocess.call([_c]+payload.split(" "))
      except ProcessLookupError:
        pass
      #print("You shouldn't run %s from pybash"%command.split()[0])
    else:
      return subprocess.Popen(command, shell=True, env=environment,
                              executable=self.settings["bash_binary"],
                              stdout=subprocess.PIPE).stdout.read().decode('utf-8')[:-1]


  def _pybashCommand(self, command):
    if not command.startswith(":"): return False
    _c, payload = command.split(" ", 1)+[""]*(2-len(command.split(" ", 1)))
    _c = _c.lstrip(":")
    if   _c in ["py", "python"]:    self.settings["bash"] = False
    elif _c in ["bash", "sh"]:      self.settings["bash"] = True
    elif _c in ["load"]:            self._loadSession(payload)
    elif _c in ["save"]:            self._saveSession(payload)
    elif _c in ['autosave']:        self.settings["autosave"] = True if payload.lower() in ['yes', 'y', 'true', '1', ''] else False
    elif _c in ['autoload']:        self.settings["autoload"] = True if payload.lower() in ['yes', 'y', 'true', '1', ''] else False
    elif _c in ["exit"]:            sys.exit()
    elif _c in ["clear"]:           os.system("cls" if WIN else "clear")
    elif _c in ["run"]:             self.runScript(payload)
    elif _c in ['help']:            print(HELP)
    elif _c in ["info", "inspect"]:
      funct=self.settings["vars"].get(payload.strip())
      print(funct.source if funct else "Unknown function")
    elif _c in ['settings']:
      for k,v in self.settings.items():
        if k not in ['history', 'globs', 'vars']:
          print("  %s: %s"%(k, repr(v)))
    elif _c in ['vars', 'variables']:
      for x, y in self.settings['vars'].items():
        if type(y) is not types.FunctionType:
          print("  %s  -  %s"%(x, repr(type(y)).split("'")[1]))
    elif _c in ['functs', 'functions']:
      for x, y in self.settings['vars'].items():
        if type(y) is types.FunctionType:
          vars = ", ".join(y.__code__.co_varnames)
          print("  %s(%s)"%(x, vars))
    else:                          print("Command not known")
    return True


  def _parseCommand(self, command):
    if self._pybashCommand(command): return
    if command.startswith("def ") and not self.settings["bash"]:
      for _command in set([x.group() for x in REG_OTHER.finditer(command)]):
        command = command.replace(_command, "_term.execBash("+repr(_command[1:-2])+")")
    for _command in set([x.group() for x in REG_OTHER.finditer(command)]):
      if self.settings["bash"]: value = self.execPython(_command[1:-2])
      else:                     value = self.execBash(_command[1:-2])
      command = command.replace(_command, repr(value))
      if not command: return
    command = command.replace("\\,", ",") # Unescape ,'s
    if self.settings["bash"]: return self.execBash(command)
    else:                     return self.execPython(command)


  def _interactiveShell(self):
    self._loadSession(auto=True)
    if not self.settings['autoload']: self._clearSession()
    multiline = None
    while True:
      try:
        data = self._input.input("... " if multiline else self._getCurs(), self.line)
        self.line = None
        if not data and not multiline:
          pass
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
        print("\nKeyboardInterrupt")
      except EOFError:
        print()
        if self.settings['autosave']: self._saveSession()
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
