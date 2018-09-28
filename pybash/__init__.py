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
  @classmethod
  def getCode(cls, text):
    return cls.__dict__.get(text.upper(), '')

# Imports
import base64
import copy
import contextlib
import getpass
import importlib
import io
import json
import marshal
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

# 'External' Packages
import pybash.bashcomplete

# Temporarily import this from an external library
#  This will be implemented better, later on.
import AdvancedInput

# Constants
REG_CURSORVARS   = re.compile("%\w+%")
REG_OTHER        = re.compile(",((?!,).)*,")
REG_BASHVARS     = re.compile("^((?!\\\\).)?(\$\w+)|(\${\w+})")
REG_PY_MULTILINE = re.compile("""^(def |if |\"\"\"((?!\"\"\").)*|\'\'\'((?!\'\'\').)*)""")
REG_ASSIGNMENT   = re.compile("^\w+\s*=")
NO_OUT = ['nano', 'vi', 'alsamixer', 'man']

WIN = True if os.name == 'nt' else False

defaultSettings={
  "bashCursor": "%red%%user%%end%@%yellow%%host%%end%:%cyan%%path%%end%$",
  "pyCursor": "%red%>>>",
  "autoload": False,
  "autosave": False,
  "session": None,
  "globs": {x:y for x,y in globals().items() if type(y)==types.ModuleType},
  "vars": {'bashcomplete':bashcomplete.bashcomplete},
  "bash": True,
  "bash_binary": "/bin/bash",
  "home": os.path.expanduser("~"),
  "history": [],
  "hooks": {'\t': bashcomplete.bashcomplete},
  "imports": []
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
exit                       - Exit pybash
hooks                      - Print the list of current hooks
hook                       - Hook a function to a key combination
unhook                     - Unhook a key combination
functs                     - Print custom functions
vars                       - Print custom variables
cursor                     - Set a custom cursor'''


@contextlib.contextmanager
def stdoutIO(stdout=None):
  old = sys.stdout
  if stdout is None:
    stdout = io.StringIO()
  sys.stdout = stdout
  yield stdout
  sys.stdout = old


class Marshaler():
  @classmethod
  def serialize(cls, obj):
    _type = repr(type(obj)).split("'")[1]
    data = obj
    if   _type == "function":
      source = obj.source if 'source' in dir(obj) else "Unknown"
      data = (base64.b64encode(marshal.dumps(obj.__code__)).decode("utf-8"),
              obj.__name__, obj.__defaults__, source)
    #elif _type == "module":
    return json.dumps((_type, data))

  @classmethod
  def deserialize(cls, encoded):
    (_type, content) = json.loads(encoded)
    if   _type == "function":
      (code, name, defaults, source) = content
      code = marshal.loads(base64.b64decode(code.encode("utf-8")))
      content =  types.FunctionType(code, globals=globals(), name=str(name), argdefs=tuple(defaults) if defaults else None)
      content.source = source
    return content


class pybash():
  def __init__(self, bash=True, bash_binary="/bin/bash"):
    self._clearSession()
    self.settings["bash"] = bash
    self.settings["bash_binary"] = bash_binary


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
    if not os.path.isabs(path): path = os.path.join(os.getcwd(), path)
    if not os.path.exists(os.path.dirname(path)): os.makedirs(os.path.dirname(path))
    try:
      _settings = copy.copy(self.settings)
      _settings.pop('session')
      # Remove unserializable objects
      _settings['vars']  = {x: Marshaler.serialize(y) for x, y in _settings['vars'].items()
                                  if type(y) is not types.ModuleType}
      _settings['globs'] = {x: y for x, y in _settings['globs'].items() if type(y) is not types.ModuleType}
      _settings['globs'] = {}
      pickle.dump(_settings, open(path, "wb"))
      self.settings['session'] = path
      print("Session saved [%s]"%path)
    except Exception as e:
      print("Could not save session! (%s)"%e)


  def _loadSession(self, path=None, auto=False):
    if not path: path = os.path.join(self.settings["home"], ".pybash/session.pkl")
    backup = self.settings
    try:
      self.settings=pickle.load(open(path, "rb"))
      self._input.history = self.settings["history"]
      self.settings['session']=path
      self.settings['vars'] = {x: Marshaler.deserialize(y) for x, y in self.settings['vars'].items()}
      imports = self.settings.pop('imports')
      self.settings['imports']=[]
      self.settings["globs"]["_term"] = self
      try:
        for i in imports:
          self.execPython(i)
      except:
        if not auto:  print("Could not reload all dependencies!")
        raise Exception
      # Reassign modules by replacing the globals
      globs = self.settings["globs"] # code reduction
      for f in [v for k, v in self.settings['vars'].items() if type(v) == types.FunctionType]:
        self.settings['vars'][f.__name__] = types.FunctionType(f.__code__, globals=self.settings['globs'],
                                                               name=f.__name__, argdefs=f.__defaults__)
      print("Session loaded [%s]"%path)
    except Exception as e:
      if not auto:
        print("Could not load session: %s"%path)
        print("Reloading last session")
      self.session = backup


  def _clearSession(self):
    self.settings = defaultSettings
    self.settings["globs"]["_term"] = self
    self._input = AdvancedInput.AdvancedInput()
    self.settings["history"] = self._input.history
    self.line = None


  def _getCurs(self):
    s = self.settings # code reduction
    curs = s['bashCursor'] if s['bash'] else s['pyCursor']
    for _x in set([y.group() for y in REG_CURSORVARS.finditer(curs)]):
      if   _x[1:-1] == "user": curs = curs.replace(_x, getpass.getuser())
      elif _x[1:-1] == "host": curs = curs.replace(_x, socket.gethostname())
      elif _x[1:-1] == "path":
        path = os.getcwd()
        if path.startswith(self.settings["home"]):
          path = path.replace(self.settings["home"], "~", 1)
        if len(curs+path)+3 > shutil.get_terminal_size().columns/2:
          path = "->/"+os.path.basename(os.path.normpath(path))
        curs = curs.replace(_x, path)
      else:
        curs = curs.replace(_x, color.getCode(_x[1:-1]))
    return curs+ color.getCode("end") + ' '


  def execPython(self, command):
    with stdoutIO() as s:
      try:
        globs = self.settings["globs"] # Code reduction
        # Check for imports to add to global
        for line in command.split("\n"):
          parts = line.strip().split(" ")
          if   len(parts) > 1 and parts[0] == "import":
            for i in [x.strip(", ") for x in parts[1:]]:
              globs[i.split(".")[0]] = importlib.import_module(i.split(".")[0])
              self.settings["imports"].append(line)
          elif len(parts) > 3 and parts[0] == "from" and parts[2] == "import ":
            for i in [x.strip(", ") for x in parts[3:]]:
              globs[i] = importlib.import_module(parts[1]).__dict__[i]
              self.settings["imports"].append(line)
        self.settings["globs"] = globs
        exec(command, globs, self.settings["vars"])
        if command.startswith("def "):
          funct = command.split(" ")[1].split("(")[0]
          self.settings["vars"][funct].source = command
      except:
        traceback.print_exc()
    return s.getvalue()[:-1]


  def execBash(self, command, redirect=False):
    environment = {x: str(y) for x, y in self.settings["vars"].items()}
    _c, payload = command.split(" ", 1)+[""]*(2-len(command.split(" ", 1)))
    if   _c == "cd":              os.chdir(payload if payload else self.settings["home"])
    elif _c in ["clear", "cls"]:  os.system("cls" if WIN else "clear")
    elif _c == "history":         self.history(payload)
    else:
      if not redirect:
        try:
          subprocess.call([_c]+payload.split(" "))
        except ProcessLookupError:
          pass
        except Exception as e:
          print("command didn't execute: %s"%e)
      else:
        try:
          return subprocess.Popen(command, shell=True, env=environment,
                                  executable=self.settings["bash_binary"],
                                  stdout=subprocess.PIPE).stdout.read().decode('utf-8')[:-1]
        except ProcessLookupError:
          pass
        except Exception as e:
          print("command didn't execute: %s"%e)

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
          vars = list(y.__code__.co_varnames)[:y.__code__.co_argcount]
          defaults = y.__defaults__ if y.__defaults__ else []
          for i, x in enumerate(defaults):
            vars[-(i+1)]="%s=%s"%(vars[-(i+1)], x)
          print("  %s(%s)"%(y.__name__, ', '.join(vars)))
    elif _c in ['hooks']:
       print('\n'.join(["  %s\t%s"%(repr(x),repr(y)) for x,y in
                        self.settings['hooks'].items()]))
    elif _c in ['hook']:
      funct = self.settings['vars'].get(payload)
      if type(funct) == types.FunctionType:
        print("Enter the key combinations and press enter")
        keys = AdvancedInput.get_raw_input()
        self.settings['hooks'][keys] = funct
      else: print("Function <%s> not found"%payload)
    elif _c in ['unhook']:
      print("Enter the key combinations and press enter")
      keys = AdvancedInput.get_raw_input()
      if keys in self.settings['hooks']: del self.settings['hooks'][keys]
      else:                              print("Key combination is not a hook")
    elif _c in ['cursor']:
      if not payload:
        print("Set a cursor string for the current language")
        print("  Variables: %path%, %user%, %host%")
        print("  Decorators: %s"%', '.join(['%%%s%%'%x.lower() for x, y in color.__dict__.items()
                                            if type(y) is str and '_' not in y]))
      else:
        cursor = 'bashCursor' if self.settings['bash'] else 'pyCursor'
        self.settings[cursor]=payload
    else:                          print("Command not known")
    return True


  def _parseCommand(self, command):
    if self._pybashCommand(command): return
    if command.startswith("def ") and not self.settings["bash"]:
      for _command in set([x.group() for x in REG_OTHER.finditer(command)]):
        command = command.replace(_command, "_term.execBash("+repr(_command[1:-2])+")")
    for _command in set([x.group() for x in REG_OTHER.finditer(command)]):
      if self.settings["bash"]: value = self.execPython(_command[1:-1])
      else:                     value = self.execBash(_command[1:-1], redirect=True)
      command = command.replace(_command, repr(value))
      if not command: return
    command = command.replace("\\,", ",") # Unescape ,'s
    # Set redirect depending on variable assignment or not
    redirect = True if REG_ASSIGNMENT.match(command) else False
    if self.settings["bash"]: return self.execBash(command, redirect=redirect)
    else:                     return self.execPython(command)


  def _interactiveShell(self):
    self._loadSession(auto=True)
    if not self.settings['autoload']: self._clearSession()
    multiline = None
    while True:
      try:
        cursor = "... " if multiline else self._getCurs()
        data = self._input.input(cursor="... " if multiline else self._getCurs(),
                                 buffer=self.line, hooks= self.settings["hooks"])
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

def main():
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

if __name__ == '__main__':
  main()
