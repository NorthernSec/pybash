import subprocess
import difflib
import AdvancedInput

def bashcomplete(buffer = None, **kwargs):
  def _files(buff=""):
    _c = "compgen -o default %s"%buff
    return subprocess.Popen(_c, shell=True, executable="/bin/bash",
                            stdout=subprocess.PIPE).stdout.read().decode('utf-8')[:-1]
  def _commands(buff=""):
    _c = "compgen -A command | grep ^%s"%buff
    return subprocess.Popen(_c, shell=True, executable="/bin/bash",
                            stdout=subprocess.PIPE).stdout.read().decode('utf-8')[:-1]

  parts = buffer.split(" ")
  match = parts[-1]
  results = None
  if ((len(parts[-2:]) == 1 or parts[-2] == "|") # Only check command options if first command or piped command
      and not buffer.endswith(" ")):             # and the buffer does not end with a space
    results, rType = _commands(match), "command"
  
  if not results:
    results, rType = _files(match), "path"
  if not results: return         # Nothing changed
  elif results.count("\n") == 0: # 1 match
    parts[-1] = results
    end = "/" if rType == "path" else " "
    return {'buffer': " ".join(parts)+end}
  else:                          # Multiple posibilities
    _to_diff = results.split("\n")
    same=_to_diff.pop(0)         # -> calculate shortest same
    for i in _to_diff:
      _diff = ''.join([x[0] for x in (difflib.ndiff(same, i))])
      same = same[:len(_diff)-len(_diff.lstrip())]
    if same == match: # Can't expand the line, ask to return options
      text="Display all %s posibilities?"%(results.count('\n')+1)
      if results.count('\n') < 15 or AdvancedInput.confirm(text):
        if rType == "path":
          results = '\n'.join([x[len(match):] for x in results.split("\n")])
        print();print(results)
    else:
      parts = buffer.split(" ")
      parts[-1] = same
      return {'buffer': " ".join(parts)}
